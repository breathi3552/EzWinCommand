package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient

class ControlController(
    private val apiClient: EzApiClient,
    private val currentDeviceKeyProvider: () -> String? = { null },
    private val onAuthInvalid: () -> Unit,
) {
    suspend fun load(): ControlUiState {
        val actionsResult = apiClient.listActions()
        val devicesResult = apiClient.listDevices()
        return when {
            actionsResult.isAuthInvalid() || devicesResult.isAuthInvalid() -> {
                onAuthInvalid()
                ControlUiState.Error("授权已失效，请重新配对。", authInvalid = true)
            }
            actionsResult is ApiResult.Success && devicesResult is ApiResult.Success -> {
                ControlUiState.Ready(actionsResult.value, devicesResult.value, currentDeviceKeyProvider()?.trim()?.takeIf { it.isNotEmpty() })
            }
            actionsResult is ApiResult.HttpError -> ControlUiState.Error(actionsResult.message, authInvalid = false)
            actionsResult is ApiResult.NetworkError -> ControlUiState.Error(actionsResult.message, authInvalid = false)
            actionsResult is ApiResult.ParseError -> ControlUiState.Error(actionsResult.message, authInvalid = false)
            devicesResult is ApiResult.HttpError -> ControlUiState.Error(devicesResult.message, authInvalid = false)
            devicesResult is ApiResult.NetworkError -> ControlUiState.Error(devicesResult.message, authInvalid = false)
            devicesResult is ApiResult.ParseError -> ControlUiState.Error(devicesResult.message, authInvalid = false)
            else -> ControlUiState.Error("加载控制页失败。", authInvalid = false)
        }
    }

    suspend fun sendAction(command: ActionCommand): CommandResult {
        return when (val result = apiClient.executeCommand(command.action, command.params)) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) {
                    onAuthInvalid()
                }
                CommandResult(success = false, message = result.message, data = emptyMap())
            }
            is ApiResult.NetworkError -> CommandResult(success = false, message = result.message, data = emptyMap())
            is ApiResult.ParseError -> CommandResult(success = false, message = result.message, data = emptyMap())
        }
    }

    suspend fun revokeDevice(deviceKey: String): Boolean {
        return when (val result = apiClient.revokeDevice(deviceKey)) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) {
                    onAuthInvalid()
                }
                false
            }
            is ApiResult.NetworkError -> false
            is ApiResult.ParseError -> false
        }
    }

    suspend fun renameDevice(deviceKey: String, name: String): Boolean {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return false
        return when (val result = apiClient.renameDevice(deviceKey, trimmed)) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) {
                    onAuthInvalid()
                }
                false
            }
            is ApiResult.NetworkError -> false
            is ApiResult.ParseError -> false
        }
    }
}

private fun <T> ApiResult<T>.isAuthInvalid(): Boolean = this is ApiResult.HttpError && (status == 401 || status == 403)
