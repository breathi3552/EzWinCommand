package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.MediaState

data class ActionCommand(
    val action: String,
    val params: Map<String, Any?> = emptyMap(),
)

sealed interface ControlUiState {
    data object Loading : ControlUiState
    data class Ready(
        val actions: List<ActionPlugin>,
        val devices: List<DeviceInfo>,
        val currentDeviceKey: String? = null,
        val media: MediaState = MediaState.LOADING,
        val mediaLoading: Boolean = true,
        val artwork: ByteArray? = null,
        val outputDevicePending: Boolean = false,
        val inputDevicePending: Boolean = false,
    ) : ControlUiState
    data class Error(
        val message: String,
        val authInvalid: Boolean,
    ) : ControlUiState
}

internal fun ControlUiState.Ready.withDevicePending(subAction: String, pending: Boolean): ControlUiState.Ready = when (subAction) {
    "set_output_device" -> copy(outputDevicePending = pending)
    "set_input_device" -> copy(inputDevicePending = pending)
    else -> this
}

fun interface ControlActionInvoker {
    suspend fun execute(command: ActionCommand): CommandResult
}

sealed interface AndroidUiState {
    data object Main : AndroidUiState
    data class Control(
        val serverId: String,
        val baseUrl: String,
        val controlState: ControlUiState = ControlUiState.Loading,
        val draft: MainDraft = MainDraft(),
        val message: String? = null,
    ) : AndroidUiState
}

data class MainDraft(
    val pcAddress: String = "",
    val pcPort: String = "",
    val pairingCode: String = "",
    val deviceName: String = "Android",
)

sealed interface AndroidUiEffect {
    data class ShowMessage(val message: String) : AndroidUiEffect
    data class OpenControl(val serverId: String, val baseUrl: String) : AndroidUiEffect
    data object ReturnToMain : AndroidUiEffect
}
