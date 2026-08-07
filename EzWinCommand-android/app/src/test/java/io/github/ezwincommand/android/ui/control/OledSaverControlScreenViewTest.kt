package io.github.ezwincommand.android.ui.control

import androidx.appcompat.app.AppCompatActivity
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.SubAction
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.Assert.assertTrue
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class OledSaverControlScreenViewTest {
    @Test
    fun `oled saver exposes only icon buttons with accessible actions`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val commands = mutableListOf<ActionCommand>()
        val plugin = ActionPlugin(
            "oled_saver",
            "OLED 护屏",
            "",
            "1.0.0",
            listOf(SubAction("turn_off", "进入护屏"), SubAction("turn_on", "恢复显示")),
        )

        screen.render(
            ControlUiState.Ready(listOf(plugin), emptyList()),
            commands::add,
            {},
            { _, _ -> },
            {},
        )

        val buttons = screen.oledButtonsForTest()
        assertEquals(2, buttons.size)
        assertEquals(listOf("进入护屏", "恢复显示"), buttons.map { it.contentDescription.toString() })
        assertTrue(buttons.all { it.importantForAccessibility == android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES })
        assertTrue(buttons.all { it.minimumWidth >= (48 * activity.resources.displayMetrics.density).toInt() })

        buttons.forEach { it.performClick() }
        assertEquals(
            listOf(
                ActionCommand("oled_saver", mapOf("sub_action" to "turn_off")),
                ActionCommand("oled_saver", mapOf("sub_action" to "turn_on")),
            ),
            commands,
        )
    }
}
