package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Test
class MediaDeviceStateTest {
    private val ready = ControlUiState.Ready(emptyList(), emptyList(), media = MediaState.LOADING)

    @Test
    fun `authoritative output update preserves input selection`() {
        val current = ready.copy(
            media = ready.media.copy(
                renderDevices = listOf(AudioEndpoint("output-old", "旧输出"), AudioEndpoint("output-new", "新输出")),
                captureDevices = listOf(AudioEndpoint("input-old", "旧输入")),
                selectedRenderId = "output-old",
                selectedCaptureId = "input-old",
            ),
        )
        val authoritative = current.media.copy(revision = 1, selectedRenderId = "output-new")

        val merged = mergeReadyWithMedia(current, authoritative, volumeBusy = false)

        assertEquals("output-new", merged.media.selectedRenderId)
        assertEquals("input-old", merged.media.selectedCaptureId)
    }

    @Test
    fun `authoritative input update preserves output selection`() {
        val current = ready.copy(
            media = ready.media.copy(
                renderDevices = listOf(AudioEndpoint("output-old", "旧输出")),
                captureDevices = listOf(AudioEndpoint("input-old", "旧输入"), AudioEndpoint("input-new", "新输入")),
                selectedRenderId = "output-old",
                selectedCaptureId = "input-old",
            ),
        )
        val authoritative = current.media.copy(revision = 2, selectedCaptureId = "input-new")

        val merged = mergeReadyWithMedia(current, authoritative, volumeBusy = false)

        assertEquals("output-old", merged.media.selectedRenderId)
        assertEquals("input-new", merged.media.selectedCaptureId)
    }
}
