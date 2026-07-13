package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.model.AudioEndpoint

internal fun mergeReadyWithMedia(
    current: ControlUiState.Ready,
    media: MediaState,
    volumeBusy: Boolean,
): ControlUiState.Ready = current.copy(
    media = mergeAuthoritativeMedia(current.media, media, volumeBusy),
    mediaLoading = false,
)

internal class DeviceSelectionGate(
    private var selectedId: String?,
) {
    private var suppressProgrammatic = true

    fun finishProgrammaticUpdate() {
        suppressProgrammatic = false
    }

    fun userSelection(endpointId: String): String? {
        if (suppressProgrammatic || endpointId == selectedId) return null
        selectedId = endpointId
        return endpointId
    }
}
internal data class DeviceSelectorOptions(
    val labels: List<String>,
    val endpointIds: List<String?>,
    val selectedIndex: Int,
)

internal fun deviceSelectorOptions(endpoints: List<AudioEndpoint>, selectedId: String?, placeholder: String): DeviceSelectorOptions {
    val selectedEndpointIndex = endpoints.indexOfFirst { it.id == selectedId }
    return if (selectedEndpointIndex >= 0) {
        DeviceSelectorOptions(endpoints.map { it.name }, endpoints.map { it.id }, selectedEndpointIndex)
    } else {
        DeviceSelectorOptions(listOf(placeholder) + endpoints.map { it.name }, listOf(null) + endpoints.map { it.id }, 0)
    }
}


internal data class DeviceSelectorAccessibility(
    val controlDescription: String,
    val optionDescription: String,
)
