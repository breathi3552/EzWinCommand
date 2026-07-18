package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.network.MediaEventTermination
import java.io.Closeable
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MediaConnectionControllerTest {
    @Test
    fun `snapshot revision is used as since and repeated eof backs off one two four seconds`() = runTest {
        val since = mutableListOf<Long>()
        val delays = mutableListOf<Long>()
        var snapshots = 0
        lateinit var controller: MediaConnectionController
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState(): ApiResult<MediaState> {
                snapshots++
                return ApiResult.Success(MediaState.LOADING.copy(revision = snapshots.toLong()))
            }
            override fun openMediaEvents(sinceRevision: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                since += sinceRevision
                onEvent(MediaState.LOADING.copy(revision = sinceRevision + 100))
                onClosed(MediaEventTermination.Eof)
                return Closeable { }
            }
        }
        controller = MediaConnectionController(
            client, "http://127.0.0.1:8080", this, StandardTestDispatcher(testScheduler),
            onState = {}, onArtwork = { _, _ -> }, onError = {}, onAuthInvalid = {},
            retryDelay = { value -> delays += value; if (delays.size == 3) controller.close() },
        )
        controller.start("owner")
        advanceUntilIdle()
        assertEquals(listOf(1L, 2L, 3L), since)
        assertEquals(listOf(1_000L, 2_000L, 4_000L), delays)
    }

    @Test
    fun `network error and server error terminations retry snapshot since with increasing backoff`() = runTest {
        val since = mutableListOf<Long>()
        val delays = mutableListOf<Long>()
        val terminations = ArrayDeque<MediaEventTermination>().apply {
            add(MediaEventTermination.NetworkError("断线"))
            add(MediaEventTermination.HttpError(500, "服务异常"))
        }
        var snapshots = 0L
        lateinit var controller: MediaConnectionController
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState(): ApiResult<MediaState> = ApiResult.Success(MediaState.LOADING.copy(revision = ++snapshots))
            override fun openMediaEvents(sinceRevision: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                since += sinceRevision
                onClosed(terminations.removeFirst())
                return Closeable { }
            }
        }
        controller = MediaConnectionController(
            client, "http://127.0.0.1:8080", this, StandardTestDispatcher(testScheduler),
            onState = {}, onArtwork = { _, _ -> }, onError = {}, onAuthInvalid = {},
            retryDelay = { value -> delays += value; if (delays.size == 2) controller.close() },
        )
        controller.start("owner")
        advanceUntilIdle()
        assertEquals(listOf(1L, 2L), since)
        assertEquals(listOf(1_000L, 2_000L), delays)
    }

    @Test
    fun `sse onOpen triggers authoritative refresh`() = runTest {
        var refreshes = 0
        val applied = mutableListOf<Long>()
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState() = ApiResult.Success(MediaState.LOADING.copy(revision = 1))
            override suspend fun refreshMediaState(): ApiResult<MediaState> {
                refreshes++
                return ApiResult.Success(MediaState.LOADING.copy(revision = 2))
            }
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                onOpen()
                return Closeable { }
            }
        }
        val controller = MediaConnectionController(client, "http://127.0.0.1:8080", this, StandardTestDispatcher(testScheduler), { applied += it.revision }, { _, _ -> }, {}, {})
        controller.start("owner")
        runCurrent()
        assertEquals(1, refreshes)
        assertEquals(listOf(1L, 2L), applied)
        controller.close()
    }

    @Test
    fun `401 snapshot stops without events and invokes auth once on main dispatcher`() = runTest {
        var opened = false
        var authCalls = 0
        val dispatcher = StandardTestDispatcher(testScheduler)
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState(): ApiResult<MediaState> = ApiResult.HttpError(401, "授权失效")
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                opened = true
                return Closeable { }
            }
        }
        val controller = MediaConnectionController(client, "http://127.0.0.1:8080", this, dispatcher, {}, { _, _ -> }, {}, { authCalls++ })
        controller.start("owner")
        advanceUntilIdle()
        assertFalse(opened)
        assertEquals(1, authCalls)
    }

    @Test
    fun `new owner generation drops old callbacks and unchanged cover path downloads once`() = runTest {
        val eventCallbacks = mutableListOf<(MediaState) -> Unit>()
        val closedCallbacks = mutableListOf<(MediaEventTermination) -> Unit>()
        var covers = 0
        val applied = mutableListOf<Long>()
        val dispatcher = StandardTestDispatcher(testScheduler)
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState() = ApiResult.Success(MediaState.LOADING.copy(revision = 1, cover = "/api/media/cover/same"))
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                eventCallbacks += onEvent
                closedCallbacks += onClosed
                return Closeable { onClosed(MediaEventTermination.ClosedByCaller) }
            }
            override suspend fun getMediaCover(path: String): ApiResult<ByteArray> { covers++; return ApiResult.Success(byteArrayOf(1)) }
        }
        val controller = MediaConnectionController(client, "http://127.0.0.1:8080", this, dispatcher, { applied += it.revision }, { _, _ -> }, {}, {})
        controller.start("old")
        runCurrent()
        controller.start("new")
        runCurrent()
        eventCallbacks.first()(MediaState.LOADING.copy(revision = 99, cover = "/api/media/cover/same"))
        runCurrent()
        assertFalse(applied.contains(99L))
        assertTrue(applied.isNotEmpty())
        assertEquals(1, covers)
        controller.close()
    }

    @Test
    fun `cover retries same path after transient failures`() = runTest {
        var attempts = 0
        val artwork = mutableListOf<ByteArray?>()
        val delays = mutableListOf<Long>()
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState() = ApiResult.Success(MediaState.LOADING.copy(revision = 1, cover = "/cover/a"))
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit) = Closeable { }
            override suspend fun getMediaCover(path: String): ApiResult<ByteArray> {
                attempts++
                return if (attempts < 3) ApiResult.HttpError(404, "missing") else ApiResult.Success(byteArrayOf(7))
            }
        }
        val controller = MediaConnectionController(
            client, "http://127.0.0.1:8080", this, StandardTestDispatcher(testScheduler),
            onState = {}, onArtwork = { _, bytes -> artwork += bytes }, onError = {}, onAuthInvalid = {},
            artworkRetryDelay = { delays += it },
        )
        controller.start("owner")
        advanceUntilIdle()
        assertEquals(3, attempts)
        assertEquals(listOf(1_000L, 2_000L), delays)
        assertTrue(artwork.last()!!.contentEquals(byteArrayOf(7)))
        controller.close()
    }

    @Test
    fun `new cover path cancels old retry and stale result cannot overwrite`() = runTest {
        val events = mutableListOf<(MediaState) -> Unit>()
        val requested = mutableListOf<String>()
        val artworkPaths = mutableListOf<String>()
        val oldStarted = CompletableDeferred<Unit>()
        val releaseOld = CompletableDeferred<Unit>()
        val dispatcher = StandardTestDispatcher(testScheduler)
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState() = ApiResult.Success(MediaState.LOADING.copy(revision = 1, cover = "/cover/old"))
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                events += onEvent
                return Closeable { }
            }
            override suspend fun getMediaCover(path: String): ApiResult<ByteArray> {
                requested += path
                if (path.endsWith("old")) {
                    oldStarted.complete(Unit)
                    releaseOld.await()
                    return ApiResult.Success(byteArrayOf(1))
                }
                return ApiResult.Success(byteArrayOf(9))
            }
        }
        val controller = MediaConnectionController(
            client, "http://127.0.0.1:8080", this, dispatcher,
            onState = {}, onArtwork = { path, bytes -> if (bytes != null) artworkPaths += path }, onError = {}, onAuthInvalid = {},
        )
        controller.start("owner")
        runCurrent()
        assertTrue(oldStarted.isCompleted)
        events.single()(MediaState.LOADING.copy(revision = 2, cover = "/cover/new"))
        runCurrent()
        releaseOld.complete(Unit)
        advanceUntilIdle()
        assertEquals(listOf("/cover/old", "/cover/new"), requested)
        assertEquals(listOf("/cover/new"), artworkPaths)
        controller.close()
    }


    @Test
    fun `older SSE revision cannot restore stale timeout after recovery`() = runTest {
        val events = mutableListOf<(MediaState) -> Unit>()
        val applied = mutableListOf<MediaState>()
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState() = ApiResult.Success(MediaState.LOADING.copy(revision = 2, error = null))
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit, onOpen: () -> Unit): Closeable {
                events += onEvent
                return Closeable { }
            }
        }
        val controller = MediaConnectionController(client, "http://127.0.0.1:8080", this, StandardTestDispatcher(testScheduler), { applied += it }, { _, _ -> }, {}, {})
        controller.start("owner")
        runCurrent()
        events.single()(MediaState.LOADING.copy(revision = 1, error = "媒体服务初始化超时"))
        runCurrent()
        assertTrue(applied.all { it.error == null })
        controller.close()
    }
}
