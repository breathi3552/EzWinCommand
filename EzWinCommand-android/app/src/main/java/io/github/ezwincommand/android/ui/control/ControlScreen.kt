package io.github.ezwincommand.android.ui.control

import android.app.Dialog
import android.app.AlertDialog
import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.ViewOutlineProvider
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.GridLayout
import android.widget.FrameLayout
import android.widget.PopupWindow
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.RadioButton
import android.widget.TextView
import androidx.appcompat.widget.AppCompatImageButton
import androidx.core.content.ContextCompat
import androidx.core.view.setPadding
import com.google.android.material.bottomsheet.BottomSheetDialog
import io.github.ezwincommand.android.R
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.MediaPlayback

internal data class MediaButtonSpec(
    val subAction: String,
    val icon: Int,
    val contentDescription: Int,
    val touchTargetDp: Int,
    val enabled: Boolean,
)

internal fun mediaButtonSpecs(available: Boolean, playback: MediaPlayback): List<MediaButtonSpec> = listOf(
    MediaButtonSpec("prev", R.drawable.ic_media_previous_24, if (available) R.string.media_previous else R.string.media_previous_disabled, 48, available),
    MediaButtonSpec("play_pause", if (playback == MediaPlayback.PLAYING) R.drawable.ic_media_pause_24 else R.drawable.ic_media_play_24, if (!available) R.string.media_play_pause_disabled else if (playback == MediaPlayback.PLAYING) R.string.media_pause else R.string.media_play, 56, available),
    MediaButtonSpec("next", R.drawable.ic_media_next_24, if (available) R.string.media_next else R.string.media_next_disabled, 48, available),
)


class ControlScreen(context: Context) : FrameLayout(context) {
    private var mediaSeekBar: SeekBar? = null
    private var mediaPercent: TextView? = null
    private var mediaTitle: TextView? = null
    private var mediaArtist: TextView? = null
    private var mediaStatus: TextView? = null
    private var mediaButtons: List<AppCompatImageButton> = emptyList()
    private var outputSelector: Button? = null
    private var inputSelector: Button? = null
    private var mediaError: TextView? = null
    private var mediaAction: ((ActionCommand) -> Unit)? = null
    private var currentDevices: List<DeviceInfo> = emptyList()
    private var currentDeviceKey: String? = null
    private var revokeDevice: ((String) -> Unit)? = null
    private var renameDevice: ((String, String) -> Unit)? = null
    private var backToPairing: (() -> Unit)? = null
    private var refreshMedia: (() -> Unit)? = null
    private var devicesPopup: PopupWindow? = null
    private var deleteDialog: AlertDialog? = null
    private val contentScroll = ScrollView(context)
    private val header = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setBackgroundColor(color(R.color.ezwin_background)); setPadding(dp(12), dp(8), dp(12), dp(8)) }
    private val root = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    private val actionsContainer = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }

    init {
        setBackgroundColor(color(R.color.ezwin_background))
        contentScroll.addView(root, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        addView(contentScroll, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT).apply { topMargin = dp(64) })
        header.addView(AppCompatImageButton(context).apply { setImageResource(R.drawable.ic_arrow_back_24); contentDescription = context.getString(R.string.main_back_to_pairing); setBackgroundResource(R.drawable.media_icon_button); setOnClickListener { backToPairing?.invoke() } }, LinearLayout.LayoutParams(dp(48), dp(48)))
        header.addView(View(context), LinearLayout.LayoutParams(0, 1, 1f))
        header.addView(AppCompatImageButton(context).apply {
            id = R.id.control_device_management
            setImageResource(R.drawable.ic_devices_24)
            contentDescription = context.getString(R.string.control_device_management)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
            isFocusable = true
            isClickable = true
            setBackgroundResource(R.drawable.media_icon_button)
            setOnClickListener { showDevicesPopup(this) }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        addView(header, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(64), Gravity.TOP))
        root.addView(actionsContainer)
    }
    fun updateLocalVolume(value: Int) {
        mediaSeekBar?.let { if (it.progress != value) it.progress = value }
        mediaPercent?.text = context.getString(R.string.media_volume_percent, value)
    }

    internal fun mediaSelectorsForTest(): Pair<Button?, Button?> = outputSelector to inputSelector
    internal fun devicesPopupForTest(): PopupWindow? = devicesPopup
    internal fun deleteDialogForTest(): AlertDialog? = deleteDialog

    fun updateMediaStateExcludingVolume(ready: ControlUiState.Ready) {
        val state = ready.media
        val available = state.available && !ready.mediaLoading
        mediaTitle?.text = state.title ?: context.getString(R.string.media_no_content)
        mediaArtist?.text = state.artist ?: context.getString(R.string.media_artist_unknown)
        mediaStatus?.text = when {
            !available -> context.getString(R.string.media_no_content)
            state.playback == MediaPlayback.PLAYING -> context.getString(R.string.media_playing)
            state.playback == MediaPlayback.PAUSED -> context.getString(R.string.media_paused)
            else -> context.getString(R.string.media_stopped)
        }
        val specs = mediaButtonSpecs(available, state.playback)
        mediaButtons.forEachIndexed { index, button ->
            val spec = specs[index]
            button.setImageResource(spec.icon)
            button.contentDescription = context.getString(spec.contentDescription)
            button.isEnabled = spec.enabled
            button.alpha = if (spec.enabled) 1f else .38f
        }
        outputSelector?.let { configureDeviceButton(it, state.renderDevices, state.selectedRenderId, ready.mediaLoading || ready.outputDevicePending, "set_output_device") }
        inputSelector?.let { configureDeviceButton(it, state.captureDevices, state.selectedCaptureId, ready.mediaLoading || ready.inputDevicePending, "set_input_device") }
        mediaError?.apply { text = state.error.orEmpty(); visibility = if (state.error.isNullOrBlank()) View.GONE else View.VISIBLE }
    }

    fun render(
        state: ControlUiState,
        onAction: (ActionCommand) -> Unit,
        onRevokeDevice: (String) -> Unit,
        onRenameDevice: (String, String) -> Unit,
        onBackToPairing: () -> Unit,
        onMediaRefresh: () -> Unit = {},
    ) {
        revokeDevice = onRevokeDevice
        renameDevice = onRenameDevice
        backToPairing = onBackToPairing
        refreshMedia = onMediaRefresh
        when (state) {
            ControlUiState.Loading -> renderActions(listOf(ActionPlugin("media", context.getString(R.string.media_title), "", "", emptyList())), state, onAction, onBackToPairing)
            is ControlUiState.Error -> { actionsContainer.removeAllViews(); actionsContainer.addView(emptyView(state.message)) }
            is ControlUiState.Ready -> { currentDevices = state.devices; currentDeviceKey = state.currentDeviceKey; renderActions(state.actions, state, onAction, onBackToPairing) }
        }
    }

    internal fun renderActions(actions: List<ActionPlugin>, state: ControlUiState, onAction: (ActionCommand) -> Unit, onBack: () -> Unit) {
        actionsContainer.removeAllViews()
        if (actions.isEmpty()) { actionsContainer.addView(emptyView(context.getString(R.string.control_no_actions)), verticalParams(dp(12))); return }
        actions.forEach { plugin ->
            val card = if (plugin.name == "media") mediaCard(state as? ControlUiState.Ready, onAction) else pluginCard(plugin, onAction)
            actionsContainer.addView(card, verticalParams(dimen(R.dimen.media_card_spacing)).apply { leftMargin = dimen(R.dimen.media_card_horizontal_margin); rightMargin = dimen(R.dimen.media_card_horizontal_margin) })
        }
    }

    private fun mediaCard(ready: ControlUiState.Ready?, onAction: (ActionCommand) -> Unit): LinearLayout {
        val state = ready?.media
        val loading = ready == null || ready.mediaLoading
        val available = state?.available == true && !loading
        mediaAction = onAction
        return panel().apply {
            val mediaHotspot = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                isClickable = true; isFocusable = true
                contentDescription = context.getString(R.string.media_refresh)
                setBackgroundResource(R.drawable.media_refresh_ripple)
                setOnClickListener { refreshMedia?.invoke() }
            }
            val cover = ImageView(context).apply {
                scaleType = ImageView.ScaleType.CENTER_CROP
                outlineProvider = object : ViewOutlineProvider() { override fun getOutline(view: View, outline: android.graphics.Outline) { outline.setRoundRect(0, 0, view.width, view.height, dp(14).toFloat()) } }
                clipToOutline = true; setBackgroundColor(color(R.color.ezwin_panel_alt))
                val bitmap = ready?.artwork?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                if (bitmap == null) setImageResource(R.drawable.ic_album_placeholder_48) else setImageBitmap(bitmap)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            }
            mediaHotspot.addView(cover, LinearLayout.LayoutParams(dimen(R.dimen.media_cover_size), dimen(R.dimen.media_cover_size)))
            val texts = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }
            mediaTitle = singleLine(state?.title ?: if (loading) context.getString(R.string.media_loading) else context.getString(R.string.media_no_content), 16f, true)
            mediaArtist = singleLine(state?.artist ?: context.getString(R.string.media_artist_unknown), 14f, false)
            texts.addView(mediaTitle); texts.addView(mediaArtist, verticalParams(dp(6)))
            val status = when { loading -> context.getString(R.string.media_loading); !available -> context.getString(R.string.media_no_content); state?.playback == MediaPlayback.PLAYING -> context.getString(R.string.media_playing); state?.playback == MediaPlayback.PAUSED -> context.getString(R.string.media_paused); else -> context.getString(R.string.media_stopped) }
            mediaStatus = metaText(status); texts.addView(mediaStatus, verticalParams(dp(6)))
            mediaHotspot.addView(texts, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dimen(R.dimen.media_header_gap) })
            addView(mediaHotspot)

            val controls = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER }
            mediaButtons = mediaButtonSpecs(available, state?.playback ?: MediaPlayback.NONE).mapIndexed { index, spec ->
                mediaButton(spec.icon, spec.contentDescription, spec.enabled) { onAction(mediaCommand(spec.subAction)) }.also { button ->
                    controls.addView(button, LinearLayout.LayoutParams(dimen(if (spec.touchTargetDp == 56) R.dimen.media_play_touch_target else R.dimen.media_touch_target), dimen(if (spec.touchTargetDp == 56) R.dimen.media_play_touch_target else R.dimen.media_touch_target)).apply {
                        if (index == 1) { leftMargin = dimen(R.dimen.media_control_gap); rightMargin = dimen(R.dimen.media_control_gap) }
                    })
                }
            }
            addView(controls, verticalParams(dimen(R.dimen.media_section_gap)))

            val volumeRow = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            volumeRow.addView(ImageView(context).apply { setImageResource(R.drawable.ic_volume_24); importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }, LinearLayout.LayoutParams(dp(24), dp(24)))
            val percent = bodyText(context.getString(R.string.media_volume_percent, state?.volume ?: 0))
            mediaPercent = percent
            volumeRow.addView(percent, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dp(8) })
            addView(volumeRow, verticalParams(dimen(R.dimen.media_section_gap)))
            val seek = SeekBar(context).apply {
                max = 100; progress = state?.volume ?: 0; isEnabled = !loading; minHeight = dimen(R.dimen.media_seek_height)
                contentDescription = context.getString(R.string.media_volume_control)
                setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(bar: SeekBar, value: Int, fromUser: Boolean) {
                        if (fromUser) {
                            percent.text = context.getString(R.string.media_volume_percent, value)
                            onAction(mediaCommand("set_volume", "volume", value).copy(params = mapOf("sub_action" to "set_volume", "volume" to value, "finish" to false)))
                        }
                    }
                    override fun onStartTrackingTouch(bar: SeekBar) = Unit
                    override fun onStopTrackingTouch(bar: SeekBar) { onAction(mediaCommand("set_volume", "volume", bar.progress).copy(params = mapOf("sub_action" to "set_volume", "volume" to bar.progress, "finish" to true))) }
                })
            }
            mediaSeekBar = seek
            addView(seek, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dimen(R.dimen.media_seek_height)))
            addView(View(context).apply { setBackgroundColor(color(R.color.ezwin_border)) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dimen(R.dimen.media_divider_height)).apply { topMargin = dimen(R.dimen.media_section_gap); bottomMargin = dimen(R.dimen.media_section_gap) })
            outputSelector = addDeviceSelector(R.drawable.ic_speaker_20, R.string.media_output_device, R.string.media_select_output, state?.renderDevices.orEmpty(), state?.selectedRenderId, loading || ready?.outputDevicePending == true, "set_output_device", onAction)
            inputSelector = addDeviceSelector(R.drawable.ic_microphone_20, R.string.media_input_device, R.string.media_select_input, state?.captureDevices.orEmpty(), state?.selectedCaptureId, loading || ready?.inputDevicePending == true, "set_input_device", onAction)
            mediaError = metaText(state?.error.orEmpty()).apply { setTextColor(color(R.color.ezwin_error)); visibility = if (state?.error.isNullOrBlank()) View.GONE else View.VISIBLE }
            addView(mediaError, verticalParams(dp(12)))
        }
    }

    private fun LinearLayout.addDeviceSelector(icon: Int, label: Int, description: Int, endpoints: List<AudioEndpoint>, selectedId: String?, disabled: Boolean, command: String, onAction: (ActionCommand) -> Unit): Button {
        val title = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        title.addView(ImageView(context).apply { setImageResource(icon); importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }, LinearLayout.LayoutParams(dp(20), dp(20)))
        title.addView(bodyText(context.getString(label)), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dp(8) })
        addView(title, verticalParams(if (childCount > 6) dp(12) else 0))
        val button = secondaryButton("") { showDeviceSheet(endpoints, selectedId, command, onAction) }
        button.contentDescription = context.getString(description)
        configureDeviceButton(button, endpoints, selectedId, disabled, command)
        addView(button, verticalParams(dp(6)))
        return button
    }

    private fun configureDeviceButton(button: Button, endpoints: List<AudioEndpoint>, selectedId: String?, disabled: Boolean, command: String) {
        button.text = endpoints.firstOrNull { it.id == selectedId }?.name
            ?: context.getString(if (endpoints.isEmpty()) if (disabled) R.string.media_devices_loading else R.string.media_no_devices else R.string.media_choose_device)
        button.isEnabled = !disabled && endpoints.isNotEmpty()
        button.setOnClickListener { showDeviceSheet(endpoints, selectedId, command, mediaAction ?: return@setOnClickListener) }
    }

    private fun showDeviceSheet(endpoints: List<AudioEndpoint>, selectedId: String?, command: String, onAction: (ActionCommand) -> Unit) {
        if (endpoints.isEmpty()) return
        val dialog = BottomSheetDialog(context)
        val content = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(color(R.color.ezwin_panel))
            setPadding(dp(16))
            addView(singleLine(context.getString(if (command == "set_output_device") R.string.media_select_output else R.string.media_select_input), 18f, true))
        }
        val list = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        endpoints.forEach { endpoint ->
            list.addView(RadioButton(context).apply {
                text = endpoint.name
                setTextColor(color(R.color.ezwin_text))
                isChecked = endpoint.id == selectedId
                minHeight = dp(52)
                setOnClickListener {
                    if (endpoint.id != selectedId) onAction(mediaCommand(command, "endpoint_id", endpoint.id))
                    dialog.dismiss()
                }
            })
        }
        content.addView(ScrollView(context).apply { addView(list) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(360)))
        dialog.setContentView(content)
        dialog.show()
    }

    private fun mediaCommand(subAction: String, key: String? = null, value: Any? = null) = ActionCommand("media", buildMap { put("sub_action", subAction); if (key != null) put(key, value) })
    private fun pluginCard(plugin: ActionPlugin, onAction: (ActionCommand) -> Unit) = panel().apply {
        addView(singleLine(plugin.label, 15f, true))
        if (plugin.subActions.isEmpty()) addView(primaryButton(plugin.label) { onAction(ActionCommand(plugin.name)) }, verticalParams(dp(12))) else addView(GridLayout(context).apply {
            columnCount = 2
            plugin.subActions.forEach { sub -> addView(primaryButton(sub.label) { onAction(ActionCommand(plugin.name, mapOf("sub_action" to sub.id))) }, gridParams()) }
        }, verticalParams(dp(12)))
    }

    private fun mediaButton(icon: Int, description: Int, enabled: Boolean, click: () -> Unit) = AppCompatImageButton(context).apply { setImageResource(icon); setBackgroundResource(R.drawable.media_icon_button); contentDescription = context.getString(description); isEnabled = enabled; alpha = if (enabled) 1f else .38f; setOnClickListener { click() } }

    fun renderDevices(devices: List<DeviceInfo>, current: String?, revoke: (String) -> Unit, rename: (String, String) -> Unit) { currentDevices = devices; currentDeviceKey = current; revokeDevice = revoke; renameDevice = rename }
    private fun showDevicesPopup(anchor: View) {
        val list = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; setBackgroundResource(R.drawable.ez_panel); setPadding(dp(12)) }
        if (currentDevices.isEmpty()) list.addView(metaText(context.getString(R.string.media_no_devices)))
        currentDevices.forEach { device ->
            val row = LinearLayout(context).apply {
                id = R.id.control_device_row
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = dp(56)
            }
            row.addView(bodyText(device.name.ifBlank { device.key }), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            if (device.key == currentDeviceKey) {
                row.addView(metaText(context.getString(R.string.control_current_device)).apply {
                    id = R.id.control_current_device_badge
                    setTextColor(color(R.color.ezwin_text))
                    setBackgroundResource(R.drawable.device_current_chip)
                    contentDescription = context.getString(R.string.control_current_device)
                }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginEnd = dp(4) })
            }
            row.addView(deviceIconButton(R.id.control_rename_device, R.drawable.ic_edit_24, context.getString(R.string.control_rename_device_description, device.name.ifBlank { device.key })) {
                showRenameDialog(device) { key, name -> renameDevice?.invoke(key, name) }
            }, LinearLayout.LayoutParams(dp(48), dp(48)))
            row.addView(deviceIconButton(R.id.control_delete_device, R.drawable.ic_delete_24, context.getString(R.string.control_delete_device_description, device.name.ifBlank { device.key })) {
                confirmDeleteDevice(device)
            }, LinearLayout.LayoutParams(dp(48), dp(48)))
            list.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        devicesPopup = PopupWindow(list, dp(360), ViewGroup.LayoutParams.WRAP_CONTENT, true).apply { isOutsideTouchable = true; setBackgroundDrawable(ColorDrawable(color(R.color.ezwin_panel))); elevation = dp(8).toFloat(); showAsDropDown(anchor, -dp(312), 0) }
    }
    private fun deviceIconButton(viewId: Int, icon: Int, description: String, click: () -> Unit) = AppCompatImageButton(context).apply {
        id = viewId
        setImageResource(icon)
        setBackgroundResource(R.drawable.media_icon_button)
        contentDescription = description
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        minimumWidth = dp(48)
        minimumHeight = dp(48)
        isFocusable = true
        setOnClickListener { click() }
    }
    private fun confirmDeleteDevice(device: DeviceInfo) {
        deleteDialog = AlertDialog.Builder(context).setTitle(R.string.control_delete_device_title).setMessage(context.getString(R.string.control_delete_device_confirm, device.name.ifBlank { device.key })).setNegativeButton(android.R.string.cancel, null).setPositiveButton(R.string.control_delete_device) { _, _ -> revokeDevice?.invoke(device.key) }.show()
    }
    private fun showRenameDialog(device: DeviceInfo, rename: (String, String) -> Unit) {
        val dialog = Dialog(context); val content = panel(); val input = EditText(context).apply { setText(device.name); setTextColor(color(R.color.ezwin_text)); setBackgroundResource(R.drawable.ez_input) }
        content.addView(input); content.addView(primaryButton(context.getString(R.string.control_rename_device)) { dialog.dismiss(); rename(device.key, input.text.toString()) }); dialog.setContentView(content); dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT)); dialog.show()
    }
    fun showResult(result: CommandResult) = result.message
    private fun panel() = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL; setBackgroundResource(R.drawable.ez_panel); setPadding(dp(16)) }
    private fun singleLine(value: String, size: Float, bold: Boolean) = TextView(context).apply { text = value; textSize = size; setTextColor(color(R.color.ezwin_text)); maxLines = 1; ellipsize = TextUtils.TruncateAt.END; if (bold) typeface = Typeface.DEFAULT_BOLD }
    private fun bodyText(value: String) = singleLine(value, 14f, false)
    private fun metaText(value: String) = singleLine(value, 12f, false).apply { setTextColor(color(R.color.ezwin_text_muted)) }
    private fun emptyView(value: String) = metaText(value).apply { gravity = Gravity.CENTER; setPadding(dp(16), dp(32), dp(16), dp(32)) }
    private fun primaryButton(value: String, click: () -> Unit) = Button(context).apply { text = value; isAllCaps = false; setTextColor(color(R.color.ezwin_text)); setBackgroundResource(R.drawable.ez_button_primary); minHeight = dp(48); setOnClickListener { click() } }
    private fun secondaryButton(value: String, click: () -> Unit) = Button(context).apply { text = value; isAllCaps = false; setTextColor(color(R.color.ezwin_text)); setBackgroundResource(R.drawable.ez_input); minHeight = dp(48); setOnClickListener { click() } }
    private fun iconButtonParams() = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52))
    private fun verticalParams(top: Int) = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top }
    private fun gridParams() = GridLayout.LayoutParams().apply { width = 0; columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f); setMargins(dp(4), dp(4), dp(4), dp(4)) }
    private fun dimen(id: Int) = resources.getDimensionPixelSize(id)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun color(id: Int) = ContextCompat.getColor(context, id)
}
