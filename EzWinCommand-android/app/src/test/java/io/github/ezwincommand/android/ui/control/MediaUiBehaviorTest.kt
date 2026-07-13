package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaUiBehaviorTest {
    @Test
    fun `pending survives SSE merge and clears only after request finally`() {
        val base = ControlUiState.Ready(emptyList(), emptyList(), media = MediaState.LOADING)
        val pending = base.withDevicePending("set_output_device", true)
        val afterSse = mergeReadyWithMedia(pending, MediaState.LOADING.copy(revision = 2, title = "新歌"), volumeBusy = false)
        assertTrue(afterSse.outputDevicePending)
        assertFalse(afterSse.inputDevicePending)
        assertEquals("新歌", afterSse.media.title)
        val afterArtwork = afterSse.copy(artwork = byteArrayOf(1, 2))
        val afterError = afterArtwork.copy(media = afterArtwork.media.copy(error = "短错"))
        assertTrue(afterArtwork.outputDevicePending)
        assertTrue(afterError.outputDevicePending)
        assertEquals("短错", afterError.media.error)
        val afterFinally = afterSse.withDevicePending("set_output_device", false)
        assertFalse(afterFinally.outputDevicePending)
    }

    @Test
    fun `device pending survives volume failure and idle reductions until device finally`() {
        val base = ControlUiState.Ready(emptyList(), emptyList(), media = MediaState.LOADING.copy(volume = 30))
        val pending = base.withDevicePending("set_output_device", true)
        val afterFailure = pending.copy(media = pending.media.copy(volume = 30, error = "音量失败"))
        val afterIdle = mergeReadyWithMedia(afterFailure, MediaState.LOADING.copy(revision = 3, volume = 40), volumeBusy = false)
        assertTrue(afterFailure.outputDevicePending)
        assertTrue(afterIdle.outputDevicePending)
        assertFalse(afterIdle.withDevicePending("set_output_device", false).outputDevicePending)
    }

    @Test
    fun `programmatic selection is suppressed and placeholder enables first endpoint choice`() {
        val endpoints = listOf(AudioEndpoint("endpoint-first", "第一个设备"), AudioEndpoint("endpoint-second", "第二个设备"))
        val options = deviceSelectorOptions(endpoints, null, "请选择设备")
        assertEquals(listOf(null, "endpoint-first", "endpoint-second"), options.endpointIds)
        assertEquals(0, options.selectedIndex)
        val policy = DeviceSelectionGate(null)
        assertNull(options.endpointIds[0])
        policy.finishProgrammaticUpdate()
        assertEquals("endpoint-first", policy.userSelection(options.endpointIds[1]!!))
        assertNull(policy.userSelection("endpoint-first"))
        assertEquals("endpoint-second", policy.userSelection(options.endpointIds[2]!!))
    }

    @Test
    fun `selector accessibility retains control and full option descriptions`() {
        val endpoint = AudioEndpoint("id", "超长但完整的扬声器设备名称")
        val accessibility = DeviceSelectorAccessibility("选择输出设备", endpoint.name)
        assertEquals("选择输出设备", accessibility.controlDescription)
        assertEquals(endpoint.name, accessibility.optionDescription)
    }
}
