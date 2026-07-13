package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.network.MediaEventTermination
import java.io.Closeable
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
            override fun openMediaEvents(sinceRevision: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit): Closeable {
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
            override fun openMediaEvents(sinceRevision: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit): Closeable {
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
    fun `401 snapshot stops without events and invokes auth once on main dispatcher`() = runTest {
        var opened = false
        var authCalls = 0
        val dispatcher = StandardTestDispatcher(testScheduler)
        val client = object : EzApiClient("http://127.0.0.1:8080", { "test-device" }) {
            override suspend fun getMediaState(): ApiResult<MediaState> = ApiResult.HttpError(401, "授权失效")
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit): Closeable {
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
            override fun openMediaEvents(since: Long, onEvent: (MediaState) -> Unit, onClosed: (MediaEventTermination) -> Unit): Closeable {
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
}
