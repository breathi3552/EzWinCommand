package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MediaUiBehaviorTest {

    @Test
    fun `busy volume keeps local value while device snapshot converges`() {
        val current = ControlUiState.Ready(
            emptyList(),
            emptyList(),
            media = MediaState.LOADING.copy(
                volume = 30,
                renderDevices = listOf(AudioEndpoint("output-old", "旧输出"), AudioEndpoint("output-new", "新输出")),
                selectedRenderId = "output-old",
            ),
        )
        val authoritative = current.media.copy(revision = 3, volume = 42, selectedRenderId = "output-new")

        val busy = mergeReadyWithMedia(current, authoritative, volumeBusy = true)
        val settled = mergeReadyWithMedia(busy, authoritative, volumeBusy = false)

        assertEquals(30, busy.media.volume)
        assertEquals("output-new", busy.media.selectedRenderId)
        assertEquals(42, settled.media.volume)
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
