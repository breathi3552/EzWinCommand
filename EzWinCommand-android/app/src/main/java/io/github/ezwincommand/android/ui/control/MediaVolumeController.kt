package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MediaVolumeActor(
    private val scope: CoroutineScope,
    private val execute: suspend (Int) -> CommandResult,
    private val onLocalValue: (Int) -> Unit,
    private val onConfirmed: (Int) -> Unit,
    private val onFailure: (confirmedValue: Int, message: String) -> Unit,
    private val onIdle: () -> Unit = {},
    private val nowMillis: () -> Long = { System.nanoTime() / 1_000_000L },
    private val waitMillis: suspend (Long) -> Unit = { delay(it) },
) {
    private var job: Job? = null
    private var pending: Int? = null
    private var gestureFinal: Int? = null
    private var lastStartedAt = Long.MIN_VALUE
    private var lastSuccessful: Int? = null
    private var confirmedValue: Int = 0
    private var closed = false

    fun updateConfirmed(value: Int) {
        require(value in 0..100)
        confirmedValue = value
        if (job?.isActive != true && pending == null) onLocalValue(value)
    }

    fun submitVolume(value: Int) {
        require(value in 0..100)
        if (closed) return
        onLocalValue(value)
        pending = value
        ensureWorker()
    }

    fun finishGesture(value: Int) {
        require(value in 0..100)
        if (closed) return
        onLocalValue(value)
        gestureFinal = value
        pending = value
        ensureWorker()
    }

    fun close() {
        closed = true
        pending = null
        gestureFinal = null
        job?.cancel()
        job = null
    }

    internal fun isBusy(): Boolean = job?.isActive == true || pending != null

    private fun ensureWorker() {
        if (job?.isActive == true) return
        job = scope.launch {
            var failed = false
            while (!closed) {
                val value = pending ?: break
                pending = null
                if (value == lastSuccessful && gestureFinal == value) {
                    gestureFinal = null
                    continue
                }
                if (lastStartedAt != Long.MIN_VALUE) {
                    val remaining = 100L - (nowMillis() - lastStartedAt)
                    if (remaining > 0) waitMillis(remaining)
                }
                lastStartedAt = nowMillis()
                val result = execute(value)
                if (!result.success) {
                    pending = null
                    gestureFinal = null
                    onFailure(confirmedValue, result.message)
                    failed = true
                    break
                }
                lastSuccessful = value
                onConfirmed(value)
                if (gestureFinal == value) gestureFinal = null
            }
            if (!closed && pending == null && !failed) onIdle()
        }
    }
}
