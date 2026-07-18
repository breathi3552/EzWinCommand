package io.github.ezwincommand.android.ui.control

import android.widget.Button
import android.widget.ImageButton
import android.widget.TextView
import android.view.View
import io.github.ezwincommand.android.R
import io.github.ezwincommand.android.model.DeviceInfo
import androidx.appcompat.app.AppCompatActivity
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class MediaControlScreenViewTest {
    @Test
    fun `device selector uses bottom sheet and current selection does not submit`() {
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
        val output: Button = screen.mediaSelectorsForTest().first!!
        assertEquals("选择输出设备", output.contentDescription)
        assertTrue(output.minimumHeight >= (48 * activity.resources.displayMetrics.density).toInt())
        assertEquals("请选择设备", output.text)
        assertTrue(commands.isEmpty())
        output.performClick()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        assertTrue(commands.isEmpty())
        assertTrue(output.isClickable)
        assertTrue(output.isFocusable)
        val management = screen.findViewById<View>(R.id.control_device_management)
        assertEquals("设备管理", management.contentDescription)
        assertTrue(management.isClickable)
        assertTrue(management.isFocusable)
        assertEquals(View.IMPORTANT_FOR_ACCESSIBILITY_YES, management.importantForAccessibility)
        assertTrue(management.isAttachedToWindow)
        assertEquals(View.VISIBLE, management.visibility)
        var ancestor: android.view.ViewParent? = management.parent
        while (ancestor is View) {
            val ancestorView = ancestor as View
            assertEquals(View.VISIBLE, ancestorView.visibility)
            assertTrue(ancestorView.importantForAccessibility != View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS)
            ancestor = ancestorView.parent
        }
    }

    @Test
    fun `device popup uses icon actions current badge and delete confirmation`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val revoked = mutableListOf<String>()
        screen.renderDevices(
            listOf(DeviceInfo("current", "我的手机", null, null), DeviceInfo("other", "平板电脑", null, null)),
            "current",
            revoked::add,
            { _, _ -> },
        )

        screen.findViewById<View>(R.id.control_device_management).performClick()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        val popup = screen.devicesPopupForTest()!!.contentView
        val rows = findViews(popup) { it.id == R.id.control_device_row }
        assertEquals(2, rows.size)
        val currentRow = rows[0]
        val otherRow = rows[1]
        assertEquals("我的手机", findViews(currentRow) { it is TextView && it.id != R.id.control_current_device_badge }.single().let { (it as TextView).text.toString() })
        assertEquals("本机", currentRow.findViewById<TextView>(R.id.control_current_device_badge).text.toString())
        assertNull(otherRow.findViewById<View>(R.id.control_current_device_badge))

        val rename = currentRow.findViewById<View>(R.id.control_rename_device)
        val delete = currentRow.findViewById<View>(R.id.control_delete_device)
        assertTrue(rename is ImageButton)
        assertTrue(delete is ImageButton)
        assertFalse(rename is Button)
        assertFalse(delete is Button)
        assertEquals("重命名设备“我的手机”", rename.contentDescription)
        assertEquals("删除设备“我的手机”", delete.contentDescription)
        val minTouch = (48 * activity.resources.displayMetrics.density).toInt()
        assertTrue(rename.minimumWidth >= minTouch && rename.minimumHeight >= minTouch)
        assertTrue(delete.minimumWidth >= minTouch && delete.minimumHeight >= minTouch)

        delete.performClick()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        val dialog = screen.deleteDialogForTest()!!
        assertEquals("确定删除“我的手机”吗？", dialog.findViewById<TextView>(android.R.id.message).text.toString())
        assertTrue(revoked.isEmpty())
    }

    private fun findViews(root: View, predicate: (View) -> Boolean): List<View> {
        val matches = mutableListOf<View>()
        fun visit(view: View) {
            if (predicate(view)) matches += view
            if (view is android.view.ViewGroup) repeat(view.childCount) { visit(view.getChildAt(it)) }
        }
        visit(root)
        return matches
    }
}
