package io.github.ezwincommand.android.ui.control

import android.content.Context
import android.graphics.Typeface
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
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
    private val root = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(resources.getDimensionPixelSize(R.dimen.control_screen_padding))
    }

    private val statusText = TextView(context).apply {
        text = context.getString(R.string.control_empty_state)
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_panel)
        setPadding(dp(16))
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
        root.addView(statusText, verticalLayoutParams(top = 0))
        root.addView(actionsContainer, verticalLayoutParams(top = dp(16)))
        root.addView(devicesContainer, verticalLayoutParams(top = dp(20)))
    }

    fun render(state: ControlUiState, onAction: (ActionCommand) -> Unit, onRevokeDevice: (String) -> Unit) {
        when (state) {
            ControlUiState.Loading -> {
                statusText.setText(R.string.control_loading)
                statusText.setTextColor(color(R.color.ezwin_text))
                clearOperations()
            }
            is ControlUiState.Error -> {
                statusText.text = state.message
                statusText.setTextColor(color(R.color.ezwin_error))
                clearOperations()
            }
            is ControlUiState.Ready -> {
                statusText.text = if (state.actions.isEmpty()) context.getString(R.string.control_empty_state) else context.getString(R.string.control_actions_ready)
                statusText.setTextColor(color(R.color.ezwin_text))
                renderActions(state.actions, onAction)
                renderDevices(state.devices, onRevokeDevice)
            }
        }
    }

    fun renderActions(actions: List<ActionPlugin>, onAction: (ActionCommand) -> Unit) {
        actionsContainer.removeAllViews()
        actionsContainer.addView(sectionTitle(context.getString(R.string.control_plugins_title)))
        if (actions.isEmpty()) {
            actionsContainer.addView(emptyView(context.getString(R.string.control_no_actions)), verticalLayoutParams(top = dp(12)))
            return
        }
        actions.forEach { plugin ->
            actionsContainer.addView(pluginCard(plugin, onAction), verticalLayoutParams(top = dp(12)))
        }
    }

    fun renderDevices(devices: List<DeviceInfo>, onRevokeDevice: (String) -> Unit) {
        devicesContainer.removeAllViews()
        if (devices.isEmpty()) {
            return
        }
        devicesContainer.addView(sectionTitle(context.getString(R.string.control_devices_title)))
        devices.forEach { device ->
            devicesContainer.addView(deviceRow(device, onRevokeDevice), verticalLayoutParams(top = dp(8)))
        }
    }

    fun showResult(result: CommandResult): String {
        statusText.text = result.message
        statusText.setTextColor(color(if (result.success) R.color.ezwin_text else R.color.ezwin_error))
        return result.message
    }

    private fun clearOperations() {
        actionsContainer.removeAllViews()
        devicesContainer.removeAllViews()
    }

    private fun pluginCard(plugin: ActionPlugin, onAction: (ActionCommand) -> Unit): LinearLayout {
        return panel().apply {
            addView(pluginTitleView(plugin))
            if (plugin.description.isNotBlank()) {
                addView(bodyText(plugin.description), verticalLayoutParams(top = dp(8)))
            }
            if (plugin.version.isNotBlank()) {
                addView(metaText(context.getString(R.string.control_plugin_version, plugin.version)), verticalLayoutParams(top = dp(6)))
            }
            val subActions = plugin.subActions
            if (subActions.isEmpty()) {
                addView(primaryButton(plugin.label) {
                    onAction(ActionCommand(plugin.name))
                }, verticalLayoutParams(top = dp(12)))
            } else {
                val grid = GridLayout(context).apply {
                    columnCount = 2
                }
                subActions.forEach { subAction ->
                    grid.addView(primaryButton(subAction.label) {
                        onAction(ActionCommand(plugin.name, mapOf("sub_action" to subAction.id)))
                    }, gridButtonParams())
                }
                addView(grid, verticalLayoutParams(top = dp(12)))
            }
        }
    }

    private fun deviceRow(device: DeviceInfo, onRevokeDevice: (String) -> Unit): LinearLayout {
        return panel().apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            val info = LinearLayout(context).apply {
                orientation = LinearLayout.VERTICAL
                addView(bodyText(device.name.ifBlank { device.key }))
                addView(metaText(device.lastSeen ?: device.createdAt ?: "--"), verticalLayoutParams(top = dp(4)))
            }
            addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(dangerButton(context.getString(R.string.control_revoke_device, device.name.ifBlank { device.key })) {
                onRevokeDevice(device.key)
            })
        }
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

    private fun dangerButton(text: String, onClick: () -> Unit): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        setTextColor(color(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_button_danger)
        minHeight = dp(40)
        setOnClickListener { onClick() }
    }

    private fun verticalLayoutParams(top: Int): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = top
        }
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
