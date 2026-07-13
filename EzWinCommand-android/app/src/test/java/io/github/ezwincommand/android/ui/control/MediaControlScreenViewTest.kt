package io.github.ezwincommand.android.ui.control

import android.widget.Spinner
import androidx.appcompat.app.AppCompatActivity
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class MediaControlScreenViewTest {
    @Test
    fun `real spinner suppresses initialization and null selection can choose first endpoint`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val commands = mutableListOf<ActionCommand>()
        val media = MediaState.LOADING.copy(
            renderDevices = listOf(AudioEndpoint("first", "第一个完整设备名"), AudioEndpoint("second", "第二个设备")),
            selectedRenderId = null,
            captureDevices = emptyList(),
        )
        screen.render(
            ControlUiState.Ready(listOf(ActionPlugin("media", "媒体", "", "", emptyList())), emptyList(), media = media, mediaLoading = false),
            commands::add, {}, { _, _ -> }, {},
        )
        shadowOf(android.os.Looper.getMainLooper()).idle()
        val output: Spinner = screen.mediaSpinnersForTest().first!!
        assertEquals("选择输出设备", output.contentDescription)
        assertTrue(output.minimumHeight >= (48 * activity.resources.displayMetrics.density).toInt())
        assertEquals("请选择设备", output.selectedItem)
        assertTrue(commands.isEmpty())
        output.setSelection(1)
        output.onItemSelectedListener!!.onItemSelected(output, output.selectedView, 1, 1L)
        shadowOf(android.os.Looper.getMainLooper()).idle()
        assertEquals(1, commands.size)
        assertEquals(mapOf("sub_action" to "set_output_device", "endpoint_id" to "first"), commands.single().params)
        assertFalse(output.selectedView?.contentDescription.toString().isBlank())
    }
}
