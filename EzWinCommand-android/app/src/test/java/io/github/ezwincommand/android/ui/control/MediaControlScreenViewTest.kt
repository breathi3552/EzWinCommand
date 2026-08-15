package io.github.ezwincommand.android.ui.control

import android.view.View
import android.widget.Button
import android.widget.ImageButton
import android.widget.RadioButton
import android.widget.TextView
import io.github.ezwincommand.android.R
import io.github.ezwincommand.android.model.DeviceInfo
import androidx.appcompat.app.AppCompatActivity
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.model.MediaPlayback
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.shadows.ShadowDialog
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class MediaControlScreenViewTest {
    @Test
    fun `device selector uses bottom sheet and current selection does not submit`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val commands = mutableListOf<MediaControlIntent>()
        val media = MediaState.LOADING.copy(
            renderDevices = listOf(AudioEndpoint("first", "第一个完整设备名"), AudioEndpoint("second", "第二个设备")),
            selectedRenderId = null,
            captureDevices = emptyList(),
        )
        screen.render(
            ControlUiState.Ready(listOf(ActionPlugin("media", "媒体", "", "", emptyList())), emptyList(), media = media, mediaLoading = false),
            {}, {}, { _, _ -> }, {},
            onMediaIntent = commands::add,
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
    fun `terminal authorization error hides controls and keeps top back operation`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        var backCalls = 0

        screen.render(
            ControlUiState.Error("授权已失效，请重新配对。", authInvalid = true),
            {},
            {},
            { _, _ -> },
            { backCalls++ },
        )
        shadowOf(android.os.Looper.getMainLooper()).idle()

        val management = screen.findViewById<View>(R.id.control_device_management)
        assertEquals(View.GONE, management.visibility)
        assertFalse(management.isEnabled)
        val back = findViews(screen) {
            it.contentDescription == activity.getString(io.github.ezwincommand.android.R.string.main_back_to_pairing)
        }.single()
        assertEquals(View.VISIBLE, back.visibility)
        back.performClick()
        assertEquals(1, backCalls)
    }
    @Test
    fun `device selector keeps selection until command result`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val commands = mutableListOf<MediaControlIntent>()
        val media = MediaState.LOADING.copy(
            renderDevices = listOf(AudioEndpoint("output-old", "旧输出"), AudioEndpoint("output-new", "新输出")),
            captureDevices = listOf(AudioEndpoint("input", "输入设备")),
            selectedRenderId = "output-old",
            selectedCaptureId = "input",
        )
        val ready = ControlUiState.Ready(
            listOf(ActionPlugin("media", "媒体", "", "", emptyList())),
            emptyList(),
            media = media,
            mediaLoading = false,
        )

        screen.render(ready, {}, {}, { _, _ -> }, {}, onMediaIntent = commands::add)
        val output = screen.mediaSelectorsForTest().first!!
        assertEquals("旧输出", output.text)
        assertTrue(output.isEnabled)

        output.performClick()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        val dialog = ShadowDialog.getLatestDialog() ?: error("设备选择对话框未显示")
        assertTrue(dialog.isShowing)
        val newOption = findViews(dialog.window!!.decorView) {
            it is RadioButton && it.text.toString() == "新输出"
        }.single()
        newOption.performClick()

        assertEquals(
            listOf(MediaControlIntent.Execute(MediaAction.SetOutputDevice("output-new"))),
            commands,
        )
        assertEquals("旧输出", output.text)
        assertTrue(output.isEnabled)

        screen.updateMediaStateExcludingVolume(ready.copy(media = media.copy(error = "切换设备失败")))

        assertEquals("旧输出", output.text)
        assertTrue(output.isEnabled)
    }


    @Test
    fun `last media snapshot keeps controls usable during silent recovery`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val media = MediaState.LOADING.copy(
            revision = 8,
            available = true,
            title = "当前标题",
            artist = "当前艺术家",
            playback = MediaPlayback.PLAYING,
            volume = 42,
            renderDevices = listOf(AudioEndpoint("output", "当前输出")),
            captureDevices = listOf(AudioEndpoint("input", "当前输入")),
            selectedRenderId = "output",
            selectedCaptureId = "input",
        )
        var refreshes = 0
        screen.render(
            ControlUiState.Ready(
                listOf(ActionPlugin("media", "媒体", "", "", emptyList())),
                emptyList(),
                media = media,
                mediaLoading = false,
            ),
            {},
            {},
            { _, _ -> },
            {},
            { refreshes++ },
        )
        shadowOf(android.os.Looper.getMainLooper()).idle()

        assertEquals("当前输出", screen.mediaSelectorsForTest().first!!.text)
        assertTrue(screen.mediaSelectorsForTest().first!!.isEnabled)
        val pause = findViews(screen) {
            it is ImageButton && it.contentDescription == activity.getString(R.string.media_pause)
        }.single()
        assertTrue(pause.isEnabled)
        findViews(screen) {
            it.contentDescription == activity.getString(R.string.media_refresh)
        }.single().performClick()
        assertEquals(1, refreshes)
    }

    @Test
    fun `initial media loading and existing error presentation remain unchanged`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val loading = ControlUiState.Ready(
            listOf(ActionPlugin("media", "媒体", "", "", emptyList())),
            emptyList(),
            media = MediaState.LOADING,
            mediaLoading = true,
        )

        screen.render(loading, {}, {}, { _, _ -> }, {})
        shadowOf(android.os.Looper.getMainLooper()).idle()

        assertTrue(
            findViews(screen) {
                it is TextView && it.text.toString() == activity.getString(R.string.media_loading)
            }.isNotEmpty(),
        )
        assertEquals(activity.getString(R.string.media_devices_loading), screen.mediaSelectorsForTest().first!!.text)
        assertFalse(screen.mediaSelectorsForTest().first!!.isEnabled)

        screen.updateMediaStateExcludingVolume(
            loading.copy(media = MediaState.LOADING.copy(error = "媒体服务不可用"), mediaLoading = false),
        )
        val error = findViews(screen) {
            it is TextView && it.text.toString() == "媒体服务不可用"
        }.single()
        assertEquals(View.VISIBLE, error.visibility)
    }

    @Test
    fun `device popup uses isCurrent badge and device ids for actions`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val revoked = mutableListOf<String>()
        screen.renderDevices(
            listOf(
                DeviceInfo("current-id", "我的手机", null, null, isCurrent = true),
                DeviceInfo("other-id", "平板电脑", null, null, isCurrent = false),
            ),
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

    @Test
    fun `refreshing devices updates an already open device popup`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val initialDevices = listOf(
            DeviceInfo("current", "我的手机", null, null, isCurrent = true),
            DeviceInfo("other", "平板电脑", null, null, isCurrent = false),
        )
        screen.renderDevices(initialDevices, {}, { _, _ -> })

        screen.findViewById<View>(R.id.control_device_management).performClick()
        shadowOf(android.os.Looper.getMainLooper()).idle()
        val popup = screen.devicesPopupForTest()!!
        assertEquals(2, findViews(popup.contentView) { it.id == R.id.control_device_row }.size)

        screen.renderDevices(listOf(initialDevices[1]), {}, { _, _ -> })
        shadowOf(android.os.Looper.getMainLooper()).idle()

        val rows = findViews(popup.contentView) { it.id == R.id.control_device_row }
        assertEquals(1, rows.size)
        assertEquals("平板电脑", findViews(rows.single()) { it is TextView && it.id != R.id.control_current_device_badge }.single().let { (it as TextView).text.toString() })
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
