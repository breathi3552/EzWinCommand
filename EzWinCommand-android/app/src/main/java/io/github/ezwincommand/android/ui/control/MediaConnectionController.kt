package io.github.ezwincommand.android.ui.control

import android.util.Log
import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.network.MediaEventTermination
import java.io.Closeable
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CancellationException
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
    private var recoveryJob: Job? = null
    private var loadedCoverPath: String? = null
    private var ownerIdentity: Any = this
    private var lastAppliedRevision = -1L

    fun start(owner: Any = this) {
        invalidate()
        ownerIdentity = owner
        val generation = generationCounter.incrementAndGet()
        activeGeneration = generation
        lastAppliedRevision = -1L
        loadedCoverPath = null
        loopJob = scope.launch { runConnectionLoop(generation, owner) }
    }

    fun refresh() {
        val generation = activeGeneration
        val owner = ownerIdentity
        if (!isCurrent(generation, owner)) return
        scope.launch { applyRefresh(generation, owner) }
    }

    override fun close() {
        invalidate()
    }

    private fun invalidate() {
        activeGeneration = generationCounter.incrementAndGet()
        recoveryJob?.cancel()
        recoveryJob = null
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
                        onMain(generation, owner) { terminateAuthorization() }
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
            val termination = CompletableDeferred<MediaEventTermination>()
            var recoveryGate: CompletableDeferred<Boolean>? = null
            eventConnection = apiClient.openMediaEvents(
                since = state.revision,
                onEvent = { incoming ->
                    val gate = recoveryGate
                    scope.launch(mainDispatcher) {
                        if (gate?.await() == false) return@launch
                        if (isCurrent(generation, owner)) applyStateOnMain(generation, owner, incoming)
                    }
                },
                onClosed = { reason -> termination.complete(reason) },
                onOpen = {
                    if (isCurrent(generation, owner)) {
                        recoveryGate?.complete(false)
                        recoveryJob?.cancel()
                        val gate = CompletableDeferred<Boolean>()
                        recoveryGate = gate
                        recoveryJob = scope.launch {
                            val outcome = try {
                                applyRefresh(generation, owner, reportErrors = false)
                            } catch (cancelled: CancellationException) {
                                gate.complete(false)
                                throw cancelled
                            } catch (error: Throwable) {
                                Log.e(TAG, "event=media_recovery_failed", error)
                                RefreshOutcome.Retry
                            }
                            gate.complete(outcome == RefreshOutcome.Applied)
                            if (outcome != RefreshOutcome.Applied && isCurrent(generation, owner)) {
                                val reason = if (outcome == RefreshOutcome.AuthInvalid) {
                                    MediaEventTermination.ClosedByCaller
                                } else {
                                    MediaEventTermination.NetworkError("媒体恢复失败")
                                }
                                termination.complete(reason)
                                eventConnection?.close()
                            }
                        }
                    }
                },
            )
            val reason = try {
                termination.await()
            } finally {
                recoveryJob?.cancel()
                recoveryJob = null
                recoveryGate?.complete(false)
                recoveryGate = null
            }
            eventConnection = null
            when (reason) {
                MediaEventTermination.ClosedByCaller -> return
                MediaEventTermination.AuthorizationRevoked -> {
                    onMain(generation, owner) { terminateAuthorization() }
                    return
                }
                is MediaEventTermination.HttpError -> when {
                    reason.status == 401 || reason.status == 403 -> {
                        onMain(generation, owner) { terminateAuthorization() }
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

    private suspend fun applyRefresh(generation: Long, owner: Any, reportErrors: Boolean = true): RefreshOutcome {
        return when (val refreshed = apiClient.refreshMediaState()) {
            is ApiResult.Success -> if (refreshed.value.revision == 0L) {
                RefreshOutcome.Retry
            } else {
                applyState(generation, owner, refreshed.value)
                RefreshOutcome.Applied
            }
            is ApiResult.HttpError -> if (refreshed.status == 401 || refreshed.status == 403) {
                onMain(generation, owner) { terminateAuthorization() }
                RefreshOutcome.AuthInvalid
            } else {
                if (reportErrors) onMain(generation, owner) { onError(refreshed.message) }
                RefreshOutcome.Retry
            }
            is ApiResult.NetworkError -> {
                if (reportErrors) onMain(generation, owner) { onError(refreshed.message) }
                RefreshOutcome.Retry
            }
            is ApiResult.ParseError -> {
                if (reportErrors) onMain(generation, owner) { onError(refreshed.message) }
                RefreshOutcome.Retry
            }
        }
    }

    private suspend fun applyState(generation: Long, owner: Any, state: MediaState) {
        withContext(mainDispatcher) {
            if (isCurrent(generation, owner)) applyStateOnMain(generation, owner, state)
        }
    }

    private fun applyStateOnMain(generation: Long, owner: Any, state: MediaState) {
        if (!isCurrent(generation, owner) || state.revision == 0L || state.revision < lastAppliedRevision) return
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
                                terminateAuthorization()
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

    private fun terminateAuthorization() {
        invalidate()
        onAuthInvalid()
    }

    private suspend fun onMain(generation: Long, owner: Any, block: () -> Unit) {
        withContext(mainDispatcher) { if (isCurrent(generation, owner)) block() }
    }
    private enum class RefreshOutcome {
        Applied,
        Retry,
        AuthInvalid,
    }

    companion object {
        internal fun backoffMillis(retry: Int): Long = (1_000L shl retry.coerceAtMost(3)).coerceAtMost(8_000L)
        private const val TAG = "MediaConnectionController"
        private const val ARTWORK_ATTEMPTS = 3
    }
}
