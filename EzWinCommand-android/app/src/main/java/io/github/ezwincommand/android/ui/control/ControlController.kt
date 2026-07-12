package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.PendingCommandStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicBoolean

class ControlController(
    private val apiClient: EzApiClient,
    private val currentDeviceKeyProvider: () -> String? = { null },
    private val onAuthInvalid: () -> Unit,
    private val pendingStore: PendingCommandStore? = null,
) {
    private val commandInFlight = AtomicBoolean(false)
    private val trackingJobs = mutableMapOf<String, Job>()
    suspend fun load(): ControlUiState {
        val a = apiClient.listActions(); val d = apiClient.listDevices()
        return when { a.isAuthInvalid() || d.isAuthInvalid() -> { onAuthInvalid(); ControlUiState.Error("授权已失效，请重新配对。", true) }
            a is ApiResult.Success && d is ApiResult.Success -> ControlUiState.Ready(a.value,d.value,currentDeviceKeyProvider()?.trim()?.takeIf { it.isNotEmpty() })
            a is ApiResult.HttpError -> ControlUiState.Error(a.message,false); d is ApiResult.HttpError -> ControlUiState.Error(d.message,false)
            a is ApiResult.NetworkError -> ControlUiState.Error(a.message,false); d is ApiResult.NetworkError -> ControlUiState.Error(d.message,false)
            else -> ControlUiState.Error("加载控制页失败。",false) }
    }
    suspend fun sendAction(command: ActionCommand): CommandResult {
        if (!commandInFlight.compareAndSet(false,true)) return CommandResult(false,"命令正在执行，请稍候。",emptyMap())
        try {
            val existing = pendingStore?.get(command.action,command.params)
            if (existing != null) return CommandResult(false,"相同命令正在执行，请稍候。",emptyMap(),existing,"queued")
            return when (val r=apiClient.executeCommand(command.action,command.params)) {
                is ApiResult.Success -> {
                    val id=r.value.commandId
                    if (id != null) { pendingStore?.put(command.action,command.params,id); CommandResult(true,"命令已受理",emptyMap(),id,r.value.status ?: "queued") } else r.value
                }
                is ApiResult.HttpError -> { if(r.status==401||r.status==403) onAuthInvalid(); CommandResult(false,r.message,emptyMap()) }
                is ApiResult.NetworkError -> CommandResult(false,r.message,emptyMap())
                is ApiResult.ParseError -> CommandResult(false,r.message,emptyMap())
            }
        } finally { commandInFlight.set(false) }
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
            when(val s=apiClient.getCommandStatus(id)) {
                is ApiResult.Success -> when(s.value.status) {
                    "succeeded" -> { pendingStore?.remove(command.action,command.params); return CommandResult(true,s.value.message.orEmpty(),s.value.data?:emptyMap(),id,"succeeded") }
                    "failed" -> { pendingStore?.remove(command.action,command.params); return CommandResult(false,s.value.message ?: "命令执行失败",s.value.data?:emptyMap(),id,"failed") }
                }
                is ApiResult.HttpError -> {
                    if(s.status==401||s.status==403) { onAuthInvalid(); return CommandResult(false,s.message,emptyMap(),id) }
                    if(s.status==404||s.status==410) { pendingStore?.removeById(id); return CommandResult(false,"命令已过期或服务已重启，可重新提交。",emptyMap(),id,"expired") }
                    Unit
                }
                is ApiResult.NetworkError -> Unit
                is ApiResult.ParseError -> { lastParseError = true }
            }
            if (pollDelayMs > 0) delay(pollDelayMs)
        }
        return if (lastParseError) {
            CommandResult(false,"状态响应解析失败，可稍后重试",emptyMap(),id,"parse_error")
        } else {
            CommandResult(false,"仍在服务端执行，可稍后继续查询",emptyMap(),id,"running")
        }
    }
    fun trackPending(command: ActionCommand, scope: CoroutineScope, onResult: (CommandResult) -> Unit): Job? {
        val id = pendingStore?.get(command.action, command.params) ?: return null
        trackingJobs[id]?.let { if (it.isActive) return it }
        val job = scope.launch(Dispatchers.IO) { pollPending(command, id)?.let(onResult) }
        trackingJobs[id] = job
        job.invokeOnCompletion { synchronized(trackingJobs) { if (trackingJobs[id] === job) trackingJobs.remove(id) } }
        return job
    }
    fun trackAllPending(scope: CoroutineScope, onResult: (CommandResult) -> Unit) {
        pendingStore?.allPending()?.forEach { trackPending(ActionCommand(it.action, it.params), scope, onResult) }
    }
    fun cancelTracking() { synchronized(trackingJobs) { trackingJobs.values.forEach { it.cancel() }; trackingJobs.clear() } }
    suspend fun revokeDevice(deviceKey:String): Boolean = when(val r=apiClient.revokeDevice(deviceKey)) { is ApiResult.Success -> r.value; is ApiResult.HttpError -> { if(r.status==401||r.status==403) onAuthInvalid(); false }; else -> false }
    suspend fun renameDevice(deviceKey:String,name:String): Boolean = if(name.trim().isEmpty()) false else when(val r=apiClient.renameDevice(deviceKey,name.trim())) { is ApiResult.Success -> r.value; is ApiResult.HttpError -> { if(r.status==401||r.status==403) onAuthInvalid(); false }; else -> false }
}
private fun <T> ApiResult<T>.isAuthInvalid() = this is ApiResult.HttpError && (status==401||status==403)
