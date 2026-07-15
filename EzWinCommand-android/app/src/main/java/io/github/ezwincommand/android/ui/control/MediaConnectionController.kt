package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.network.MediaEventTermination
import java.io.Closeable
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MediaConnectionController(
    private val apiClient: EzApiClient,
    val baseUrl: String,
    private val scope: CoroutineScope,
    private val mainDispatcher: CoroutineDispatcher = Dispatchers.Main.immediate,
    private val onState: (MediaState) -> Unit,
    private val onArtwork: (path: String, bytes: ByteArray?) -> Unit,
    private val onError: (String) -> Unit,
    private val onAuthInvalid: () -> Unit,
    private val retryDelay: suspend (Long) -> Unit = { delay(it) },
    private val artworkRetryDelay: suspend (Long) -> Unit = { delay(it) },
) : Closeable {
    private val generationCounter = AtomicLong(0)
    private var activeGeneration = 0L
    private var loopJob: Job? = null
    private var eventConnection: Closeable? = null
    private var coverJob: Job? = null
    private var loadedCoverPath: String? = null
    private var ownerIdentity: Any = this
    private var lastAppliedRevision = -1L

    fun start(owner: Any = this) {
        invalidate()
        ownerIdentity = owner
        val generation = generationCounter.incrementAndGet()
        activeGeneration = generation
        lastAppliedRevision = -1L
        loopJob = scope.launch { runConnectionLoop(generation, owner) }
    }

    override fun close() {
        invalidate()
    }

    private fun invalidate() {
        activeGeneration = generationCounter.incrementAndGet()
        eventConnection?.close()
        eventConnection = null
        coverJob?.cancel()
        coverJob = null
        loopJob?.cancel()
        loopJob = null
    }

    private fun isCurrent(generation: Long, owner: Any): Boolean =
        generation == activeGeneration && owner === ownerIdentity && scope.isActive

    private suspend fun runConnectionLoop(generation: Long, owner: Any) {
        var retry = 0
        while (isCurrent(generation, owner)) {
            val snapshot = apiClient.getMediaState()
            val state = when (snapshot) {
                is ApiResult.Success -> snapshot.value
                is ApiResult.HttpError -> {
                    if (snapshot.status == 401 || snapshot.status == 403) {
                        onMain(generation, owner) { onAuthInvalid() }
                        return
                    }
                    if (snapshot.status in 400..499) {
                        onMain(generation, owner) { onError(snapshot.message) }
                        return
                    }
                    null
                }
                is ApiResult.NetworkError -> null
                is ApiResult.ParseError -> {
                    onMain(generation, owner) { onError(snapshot.message) }
                    return
                }
            }
            if (state == null) {
                retryDelay(backoffMillis(retry++))
                continue
            }
            applyState(generation, owner, state)
            val termination = kotlinx.coroutines.CompletableDeferred<MediaEventTermination>()
            eventConnection = apiClient.openMediaEvents(
                since = state.revision,
                onEvent = { incoming ->
                    scope.launch(mainDispatcher) {
                        if (isCurrent(generation, owner)) applyStateOnMain(generation, owner, incoming)
                    }
                },
                onClosed = { reason -> termination.complete(reason) },
            )
            val reason = termination.await()
            eventConnection = null
            when (reason) {
                MediaEventTermination.ClosedByCaller -> return
                is MediaEventTermination.HttpError -> when {
                    reason.status == 401 || reason.status == 403 -> {
                        onMain(generation, owner) { onAuthInvalid() }
                        return
                    }
                    reason.status in 400..499 -> {
                        onMain(generation, owner) { onError(reason.message) }
                        return
                    }
                    else -> Unit
                }
                MediaEventTermination.Eof, is MediaEventTermination.NetworkError -> Unit
            }
            retryDelay(backoffMillis(retry++))
        }
    }

    private suspend fun applyState(generation: Long, owner: Any, state: MediaState) {
        withContext(mainDispatcher) {
            if (isCurrent(generation, owner)) applyStateOnMain(generation, owner, state)
        }
    }

    private fun applyStateOnMain(generation: Long, owner: Any, state: MediaState) {
        if (!isCurrent(generation, owner) || state.revision < lastAppliedRevision) return
        lastAppliedRevision = state.revision
        onState(state)
        val path = state.cover
        if (path == loadedCoverPath) return
        loadedCoverPath = path
        coverJob?.cancel()
        coverJob = null
        if (path == null) {
            onArtwork("", null)
            return
        }
        onArtwork(path, null)
        coverJob = scope.launch {
            repeat(ARTWORK_ATTEMPTS) { attempt ->
                val result = apiClient.getMediaCover(path)
                val applied = withContext(mainDispatcher) {
                    if (!isCurrent(generation, owner) || loadedCoverPath != path) return@withContext true
                    when (result) {
                        is ApiResult.Success -> {
                            onArtwork(path, result.value)
                            true
                        }
                        is ApiResult.HttpError -> {
                            if (result.status == 401 || result.status == 403) {
                                onAuthInvalid()
                                true
                            } else result.status != 404
                        }
                        is ApiResult.NetworkError -> false
                        is ApiResult.ParseError -> true
                    }
                }
                if (applied || attempt == ARTWORK_ATTEMPTS - 1) return@launch
                artworkRetryDelay(backoffMillis(attempt))
            }
        }
    }

    private suspend fun onMain(generation: Long, owner: Any, block: () -> Unit) {
        withContext(mainDispatcher) { if (isCurrent(generation, owner)) block() }
    }

    companion object {
        internal fun backoffMillis(retry: Int): Long = (1_000L shl retry.coerceAtMost(3)).coerceAtMost(8_000L)
        private const val ARTWORK_ATTEMPTS = 3
    }
}
