package io.github.ezwincommand.android.ui.control

import androidx.appcompat.app.AppCompatActivity
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.SubAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class OledSaverControlScreenViewTest {
    @Test
    fun `oled saver exposes one rectangular enter button`() {
        val activity = Robolectric.buildActivity(AppCompatActivity::class.java).setup().get()
        val screen = ControlScreen(activity)
        activity.setContentView(screen)
        val commands = mutableListOf<ActionCommand>()
        val plugin = ActionPlugin(
            "oled_saver",
            "OLED 护屏",
            "",
            "1.1.0",
            listOf(SubAction("turn_off", "进入护屏")),
        )

        screen.render(
            ControlUiState.Ready(listOf(plugin), emptyList()),
            commands::add,
            {},
            { _, _ -> },
            {},
        )

        val button = requireNotNull(screen.oledActionButtonForTest())
        assertEquals("进入护屏", button.text.toString())
        assertEquals(false, button.isAllCaps)
        assertTrue(button.minimumHeight >= (48 * activity.resources.displayMetrics.density).toInt())

        button.performClick()
        assertEquals(
            listOf(ActionCommand("oled_saver", mapOf("sub_action" to "turn_off"))),
            commands,
        )
    }
}
