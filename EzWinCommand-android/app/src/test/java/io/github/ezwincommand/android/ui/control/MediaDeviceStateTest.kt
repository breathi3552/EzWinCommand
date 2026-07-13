package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaDeviceStateTest {
    private val ready = ControlUiState.Ready(emptyList(), emptyList(), media = MediaState.LOADING)

    @Test
    fun `slow output failure clears pending and preserves selected endpoint`() {
        val authoritative = ready.copy(media = ready.media.copy(selectedRenderId = "endpoint-one"))
        val pending = authoritative.withDevicePending("set_output_device", true)
        assertTrue(pending.outputDevicePending)
        assertFalse(pending.inputDevicePending)
        val cleared = pending.withDevicePending("set_output_device", false)
        assertFalse(cleared.outputDevicePending)
        assertEquals("endpoint-one", cleared.media.selectedRenderId)
    }

    @Test
    fun `input pending changes input only`() {
        val pending = ready.withDevicePending("set_input_device", true)
        assertFalse(pending.outputDevicePending)
        assertTrue(pending.inputDevicePending)
    }
}
