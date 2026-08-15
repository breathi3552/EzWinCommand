package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.MediaState

data class ActionCommand(
    val action: String,
    val params: Map<String, Any?> = emptyMap(),
)

sealed interface MediaAction {
    data object PlayPause : MediaAction
    data object Previous : MediaAction
    data object Next : MediaAction
    data class SetVolume(val volume: Int) : MediaAction
    data class SetOutputDevice(val endpointId: String) : MediaAction
    data class SetInputDevice(val endpointId: String) : MediaAction
}

sealed interface MediaControlIntent {
    data class Execute(val action: MediaAction) : MediaControlIntent
    data class ChangeVolume(val volume: Int) : MediaControlIntent
    data class FinishVolume(val volume: Int) : MediaControlIntent
}

sealed interface ControlUiState {
    data object Loading : ControlUiState
    data class Ready(
        val actions: List<ActionPlugin>,
        val devices: List<DeviceInfo>,
        val media: MediaState = MediaState.LOADING,
        val mediaLoading: Boolean = true,
        val artwork: ByteArray? = null,
    ) : ControlUiState
    data class Error(
        val message: String,
        val authInvalid: Boolean,
    ) : ControlUiState
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
}

internal sealed interface DeviceRevokeTransition {
    data object Failed : DeviceRevokeTransition
    data object CleanupFailed : DeviceRevokeTransition
    data object ReturnedToPairing : DeviceRevokeTransition
    data class Refreshed(val state: ControlUiState) : DeviceRevokeTransition
}

internal suspend fun applyDeviceRevoke(
    deviceId: String,
    devices: List<DeviceInfo>,
    revoke: suspend (String) -> Boolean,
    onSelfRevoked: suspend () -> Boolean,
    refresh: suspend () -> ControlUiState,
): DeviceRevokeTransition {
    if (!revoke(deviceId)) return DeviceRevokeTransition.Failed
    if (devices.firstOrNull { it.deviceId == deviceId }?.isCurrent == true) {
        return if (onSelfRevoked()) {
            DeviceRevokeTransition.ReturnedToPairing
        } else {
            DeviceRevokeTransition.CleanupFailed
        }
    }
    return DeviceRevokeTransition.Refreshed(refresh())
}
