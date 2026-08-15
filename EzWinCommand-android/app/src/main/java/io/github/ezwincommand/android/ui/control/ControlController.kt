package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.PendingCommandStore
import java.io.Closeable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

class ControlController(
    internal val apiClient: EzApiClient,
    private val onAuthInvalid: () -> Unit,
    private val pendingStore: PendingCommandStore? = null,
) : Closeable {
    private val commandInFlight = AtomicBoolean(false)
    private val authorizationInvalidated = AtomicBoolean(false)
    private val trackingJobs = mutableMapOf<String, Job>()
    suspend fun load(): ControlUiState {
        if (authorizationInvalidated.get()) return authorizationError()
        val actions = apiClient.listActions()
        if (actions.isAuthInvalid()) {
            reportAuthInvalid()
            return authorizationError()
        }
        if (authorizationInvalidated.get()) return authorizationError()
        val devices = apiClient.listDevices()
        if (devices.isAuthInvalid()) {
            reportAuthInvalid()
            return authorizationError()
        }
        if (authorizationInvalidated.get()) return authorizationError()
        val media = apiClient.getMediaState()
        if (media.isAuthInvalid()) {
            reportAuthInvalid()
            return authorizationError()
        }
        if (authorizationInvalidated.get()) return authorizationError()
        val authoritativeMedia = (media as? ApiResult.Success)?.value?.takeIf { it.revision > 0L }
        return when {
            actions is ApiResult.Success && devices is ApiResult.Success -> ControlUiState.Ready(
                actions = actions.value,
                devices = devices.value,
                media = authoritativeMedia ?: io.github.ezwincommand.android.model.MediaState.LOADING,
                mediaLoading = authoritativeMedia == null,
            )
            actions is ApiResult.HttpError -> ControlUiState.Error(actions.message, false)
            devices is ApiResult.HttpError -> ControlUiState.Error(devices.message, false)
            actions is ApiResult.NetworkError -> ControlUiState.Error(actions.message, false)
            devices is ApiResult.NetworkError -> ControlUiState.Error(devices.message, false)
            else -> ControlUiState.Error("加载控制页失败。", false)
        }
    }

    suspend fun sendMediaAction(action: MediaAction): CommandResult {
        if (authorizationInvalidated.get()) return authorizationErrorResult()
        val params: Map<String, Any?> = when (action) {
            MediaAction.PlayPause -> mapOf("sub_action" to "play_pause")
            MediaAction.Previous -> mapOf("sub_action" to "prev")
            MediaAction.Next -> mapOf("sub_action" to "next")
            is MediaAction.SetVolume -> mapOf("sub_action" to "set_volume", "volume" to action.volume)
            is MediaAction.SetOutputDevice -> mapOf("sub_action" to "set_output_device", "endpoint_id" to action.endpointId)
            is MediaAction.SetInputDevice -> mapOf("sub_action" to "set_input_device", "endpoint_id" to action.endpointId)
        }
        val result = when (val response = apiClient.executeCommand("media", params)) {
            is ApiResult.Success -> response.value
            is ApiResult.HttpError -> {
                if (response.status == 401 || response.status == 403) reportAuthInvalid()
                CommandResult(false, response.message, emptyMap())
            }
            is ApiResult.NetworkError -> CommandResult(false, response.message, emptyMap())
            is ApiResult.ParseError -> CommandResult(false, response.message, emptyMap())
        }
        return if (authorizationInvalidated.get()) authorizationErrorResult(result.commandId) else result
    }
    suspend fun sendAction(command: ActionCommand): CommandResult {
        if (authorizationInvalidated.get()) return authorizationErrorResult()
        if (!commandInFlight.compareAndSet(false, true)) return CommandResult(false, "命令正在执行，请稍候。", emptyMap())
        try {
            if (authorizationInvalidated.get()) return authorizationErrorResult()
            val existing = pendingStore?.get(command.action, command.params)
            if (existing != null) return CommandResult(false, "相同命令正在执行，请稍候。", emptyMap(), existing, "queued")
            val result = when (val response = apiClient.executeCommand(command.action, command.params)) {
                is ApiResult.Success -> {
                    val id = response.value.commandId
                    if (id != null) {
                        pendingStore?.put(command.action, command.params, id)
                        CommandResult(true, "命令已受理", emptyMap(), id, response.value.status ?: "queued")
                    } else {
                        response.value
                    }
                }
                is ApiResult.HttpError -> {
                    if (response.status == 401 || response.status == 403) reportAuthInvalid()
                    CommandResult(false, response.message, emptyMap())
                }
                is ApiResult.NetworkError -> CommandResult(false, response.message, emptyMap())
                is ApiResult.ParseError -> CommandResult(false, response.message, emptyMap())
            }
            return if (authorizationInvalidated.get()) authorizationErrorResult(result.commandId) else result
        } finally {
            commandInFlight.set(false)
        }
    }
    suspend fun pollPending(
        command: ActionCommand,
        commandId: String? = pendingStore?.get(command.action, command.params),
        maxPolls: Int = 60,
        pollDelayMs: Long = 1000,
    ): CommandResult? {
        val id = commandId ?: return null
        var lastParseError = false
        repeat(maxPolls) {
            if (authorizationInvalidated.get()) return null
            when (val status = apiClient.getCommandStatus(id)) {
                is ApiResult.Success -> {
                    if (authorizationInvalidated.get()) return null
                    when (status.value.status) {
                        "succeeded" -> {
                            pendingStore?.remove(command.action, command.params)
                            return CommandResult(true, status.value.message.orEmpty(), status.value.data ?: emptyMap(), id, "succeeded")
                        }
                        "failed" -> {
                            pendingStore?.remove(command.action, command.params)
                            return CommandResult(false, status.value.message ?: "命令执行失败", status.value.data ?: emptyMap(), id, "failed")
                        }
                    }
                }
                is ApiResult.HttpError -> {
                    if (status.status == 401 || status.status == 403) {
                        reportAuthInvalid()
                        return null
                    }
                    if (status.status == 404 || status.status == 410) {
                        pendingStore?.removeById(id)
                        return CommandResult(false, "命令已过期或服务已重启，可重新提交。", emptyMap(), id, "expired")
                    }
                }
                is ApiResult.NetworkError -> Unit
                is ApiResult.ParseError -> lastParseError = true
            }
            if (authorizationInvalidated.get()) return null
            if (pollDelayMs > 0) delay(pollDelayMs)
        }
        if (authorizationInvalidated.get()) return null
        return if (lastParseError) {
            CommandResult(false, "状态响应解析失败，可稍后重试", emptyMap(), id, "parse_error")
        } else {
            CommandResult(false, "仍在服务端执行，可稍后继续查询", emptyMap(), id, "running")
        }
    }
    fun trackPending(command: ActionCommand, scope: CoroutineScope, onResult: (CommandResult) -> Unit): Job? {
        val id = pendingStore?.get(command.action, command.params) ?: return null
        trackingJobs[id]?.let { if (it.isActive) return it }
        val job = scope.launch(Dispatchers.IO) {
            pollPending(command, id)?.let { result ->
                if (!authorizationInvalidated.get()) onResult(result)
            }
        }
        trackingJobs[id] = job
        job.invokeOnCompletion { synchronized(trackingJobs) { if (trackingJobs[id] === job) trackingJobs.remove(id) } }
        return job
    }
    fun trackAllPending(scope: CoroutineScope, onResult: (CommandResult) -> Unit) {
        if (authorizationInvalidated.get()) return
        pendingStore?.allPending()?.forEach { trackPending(ActionCommand(it.action, it.params), scope, onResult) }
    }
    fun cancelTracking() { synchronized(trackingJobs) { trackingJobs.values.forEach { it.cancel() }; trackingJobs.clear() } }
    fun invalidateAuthorization() {
        authorizationInvalidated.set(true)
        cancelTracking()
    }
    fun isAuthorizationInvalidated(): Boolean = authorizationInvalidated.get()

    private fun reportAuthInvalid() {
        val first = authorizationInvalidated.compareAndSet(false, true)
        cancelTracking()
        if (first) onAuthInvalid()
    }

    override fun close() {
        invalidateAuthorization()
        apiClient.close()
    }
    suspend fun revokeDevice(deviceId: String): Boolean {
        if (authorizationInvalidated.get()) return false
        return when (val result = apiClient.revokeDevice(deviceId)) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) reportAuthInvalid()
                false
            }
            else -> false
        }
    }

    suspend fun renameDevice(deviceId: String, name: String): Boolean =
        if (authorizationInvalidated.get() || name.trim().isEmpty()) {
            false
        } else {
            when (val result = apiClient.renameDevice(deviceId, name.trim())) {
                is ApiResult.Success -> result.value.takeUnless { authorizationInvalidated.get() } ?: false
                is ApiResult.HttpError -> {
                    if (result.status == 401 || result.status == 403) reportAuthInvalid()
                    false
                }
                else -> false
            }
        }
}

private const val AUTHORIZATION_INVALID_MESSAGE = "授权已失效，请重新配对。"

private fun ControlController.authorizationError(): ControlUiState.Error =
    ControlUiState.Error(AUTHORIZATION_INVALID_MESSAGE, true)

private fun authorizationErrorResult(commandId: String? = null): CommandResult =
    CommandResult(false, AUTHORIZATION_INVALID_MESSAGE, emptyMap(), commandId)


private fun <T> ApiResult<T>.isAuthInvalid() = this is ApiResult.HttpError && (status==401||status==403)
