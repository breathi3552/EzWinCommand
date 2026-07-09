package io.github.ezwincommand.android.ui.control

import android.content.Context
import android.graphics.Typeface
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.app.Dialog
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import androidx.core.content.ContextCompat
import androidx.core.view.setMargins
import androidx.core.view.setPadding
import io.github.ezwincommand.android.R
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo

class ControlScreen(
    context: Context,
) : ScrollView(context) {
    private var devicesExpanded: Boolean = false

    private val root = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0)
    }

    private val actionsContainer = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
    }

    private val devicesContainer = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
    }

    init {
        setBackgroundColor(color(R.color.ezwin_background))
        addView(root, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(actionsContainer, verticalLayoutParams(top = 0))
        root.addView(devicesContainer, verticalLayoutParams(top = dp(16)))
    }

    fun render(
        state: ControlUiState,
        onAction: (ActionCommand) -> Unit,
        onRevokeDevice: (String) -> Unit,
        onRenameDevice: (String, String) -> Unit,
        onBackToPairing: () -> Unit,
    ) {
        when (state) {
            ControlUiState.Loading -> {
                clearOperations()
                actionsContainer.addView(emptyView(context.getString(R.string.control_loading)))
            }
            is ControlUiState.Error -> {
                clearOperations()
                actionsContainer.addView(emptyView(state.message))
            }
            is ControlUiState.Ready -> {
                renderActions(state.actions, onAction, onBackToPairing)
                renderDevices(state.devices, state.currentDeviceKey, onRevokeDevice, onRenameDevice)
            }
        }
    }

    fun renderActions(actions: List<ActionPlugin>, onAction: (ActionCommand) -> Unit, onBackToPairing: () -> Unit) {
        actionsContainer.removeAllViews()
        actionsContainer.addView(backIconButton(onBackToPairing), iconButtonParams())
        if (actions.isEmpty()) {
            actionsContainer.addView(emptyView(context.getString(R.string.control_no_actions)), verticalLayoutParams(top = dp(12)))
            return
        }
        actions.forEach { plugin ->
            actionsContainer.addView(pluginCard(plugin, onAction), verticalLayoutParams(top = dp(10)))
        }
    }

    fun renderDevices(
        devices: List<DeviceInfo>,
        currentDeviceKey: String?,
        onRevokeDevice: (String) -> Unit,
        onRenameDevice: (String, String) -> Unit,
    ) {
        devicesContainer.removeAllViews()
        if (devices.isEmpty()) return
        val title = context.getString(
            if (devicesExpanded) R.string.control_devices_expanded else R.string.control_devices_collapsed,
            devices.size,
        )
        devicesContainer.addView(secondaryButton(title) {
            devicesExpanded = !devicesExpanded
            renderDevices(devices, currentDeviceKey, onRevokeDevice, onRenameDevice)
        })
        if (!devicesExpanded) return
        devices.forEach { device ->
            devicesContainer.addView(deviceRow(device, currentDeviceKey == device.key, onRevokeDevice, onRenameDevice), verticalLayoutParams(top = dp(8)))
        }
    }

    fun showResult(result: CommandResult): String {
        return result.message
    }

    private fun clearOperations() {
        actionsContainer.removeAllViews()
        devicesContainer.removeAllViews()
    }

    private fun pluginCard(plugin: ActionPlugin, onAction: (ActionCommand) -> Unit): LinearLayout {
        return panel().apply {
            addView(pluginTitleView(plugin))
            val subActions = plugin.subActions
            if (subActions.isEmpty()) {
                addView(primaryButton(plugin.label) { onAction(ActionCommand(plugin.name)) }, verticalLayoutParams(top = dp(12)))
            } else {
                val grid = GridLayout(context).apply { columnCount = 2 }
                subActions.forEach { subAction ->
                    grid.addView(primaryButton(subAction.label) {
                        onAction(ActionCommand(plugin.name, mapOf("sub_action" to subAction.id)))
                    }, gridButtonParams())
                }
                addView(grid, verticalLayoutParams(top = dp(12)))
            }
        }
    }

    private fun deviceRow(
        device: DeviceInfo,
        isCurrentDevice: Boolean,
        onRevokeDevice: (String) -> Unit,
        onRenameDevice: (String, String) -> Unit,
    ): LinearLayout {
        return panel().apply {
            val title = if (isCurrentDevice) {
                "${device.name.ifBlank { device.key }} · ${context.getString(R.string.control_current_device)}"
            } else {
                device.name.ifBlank { device.key }
            }
            addView(bodyText(title))
            val buttons = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.END
                addView(iconActionButton("✎", R.drawable.ez_input) {
                    showRenameDialog(device, onRenameDevice)
                }, iconButtonParams())
                addView(iconActionButton("×", R.drawable.ez_button_danger) {
                    onRevokeDevice(device.key)
                }, iconButtonParams().apply { leftMargin = dp(8) })
            }
            addView(buttons, verticalLayoutParams(top = dp(10)))
        }
    }

    private fun showRenameDialog(device: DeviceInfo, onRenameDevice: (String, String) -> Unit) {
        val dialog = Dialog(context)
        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.ez_panel)
            setPadding(dp(24))
        }
        content.addView(sectionTitle(context.getString(R.string.control_rename_device_title)))
        val input = EditText(context).apply {
            setText(device.name)
            hint = context.getString(R.string.main_device_name_hint)
            setTextColor(color(R.color.ezwin_text))
            setHintTextColor(color(R.color.ezwin_text_muted))
            setBackgroundResource(R.drawable.ez_input)
            setPadding(dp(12))
        }
        content.addView(input, verticalLayoutParams(top = dp(12)))
        val actions = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(secondaryButton(context.getString(R.string.main_pair_dialog_negative)) { dialog.dismiss() }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(8) })
        actions.addView(primaryButton(context.getString(R.string.control_rename_device)) {
            dialog.dismiss()
            onRenameDevice(device.key, input.text?.toString().orEmpty())
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        content.addView(actions, verticalLayoutParams(top = dp(16)))
        dialog.setContentView(content)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.show()
        dialog.window?.setLayout((resources.displayMetrics.widthPixels * 0.9f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun panel(): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.ez_panel)
        setPadding(dp(16))
    }

    private fun sectionTitle(text: String): TextView = TextView(context).apply {
        this.text = text
        setTextColor(color(R.color.ezwin_text))
        textSize = 16f
        typeface = Typeface.DEFAULT_BOLD
    }

    private fun pluginTitleView(plugin: ActionPlugin): TextView = TextView(context).apply {
        text = plugin.label
        setTextColor(color(R.color.ezwin_text))
        textSize = 15f
        typeface = Typeface.DEFAULT_BOLD
    }

    private fun bodyText(text: String): TextView = TextView(context).apply {
        this.text = text
        setTextColor(color(R.color.ezwin_text))
        textSize = 14f
        gravity = Gravity.START
    }

    private fun metaText(text: String): TextView = TextView(context).apply {
        this.text = text
        setTextColor(color(R.color.ezwin_text_muted))
        textSize = 12f
        gravity = Gravity.START
    }

    private fun emptyView(text: String): TextView = metaText(text).apply {
        gravity = Gravity.CENTER
        setPadding(dp(16), dp(32), dp(16), dp(32))
    }

    private fun primaryButton(text: String, onClick: () -> Unit): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        setTextColor(color(R.color.ezwin_text))
        typeface = Typeface.DEFAULT_BOLD
        setBackgroundResource(R.drawable.ez_button_primary)
        minHeight = dp(48)
        setOnClickListener { onClick() }
    }


    private fun backIconButton(onClick: () -> Unit): Button = Button(context).apply {
        text = "‹"
        isAllCaps = false
        textSize = 30f
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_input)
        minWidth = dp(48)
        minHeight = dp(48)
        setOnClickListener { onClick() }
    }

    private fun iconActionButton(text: String, background: Int, onClick: () -> Unit): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        textSize = 20f
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(background)
        minWidth = dp(44)
        minHeight = dp(44)
        setOnClickListener { onClick() }
    }

    private fun secondaryButton(text: String, onClick: () -> Unit): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_input)
        minHeight = dp(44)
        setOnClickListener { onClick() }
    }

    private fun dangerButton(text: String, onClick: () -> Unit): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_button_danger)
        minHeight = dp(40)
        setOnClickListener { onClick() }
    }

    private fun iconButtonParams(): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(dp(52), dp(52)).apply { gravity = Gravity.START }
    }

    private fun verticalLayoutParams(top: Int): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top }
    }

    private fun gridButtonParams(): GridLayout.LayoutParams {
        return GridLayout.LayoutParams().apply {
            width = 0
            height = ViewGroup.LayoutParams.WRAP_CONTENT
            columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
            setMargins(dp(4))
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun color(id: Int): Int = ContextCompat.getColor(context, id)
}
