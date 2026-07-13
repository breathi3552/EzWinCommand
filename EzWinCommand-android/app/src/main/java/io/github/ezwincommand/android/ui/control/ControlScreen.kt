package io.github.ezwincommand.android.ui.control

import android.app.Dialog
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
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.widget.AppCompatImageButton
import androidx.core.content.ContextCompat
import androidx.core.view.setPadding
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


class ControlScreen(context: Context) : ScrollView(context) {
    private var devicesExpanded = false
    private var renderingSpinner = false
    private var mediaSeekBar: SeekBar? = null
    private var mediaPercent: TextView? = null
    private var mediaTitle: TextView? = null
    private var mediaArtist: TextView? = null
    private var mediaStatus: TextView? = null
    private var mediaButtons: List<AppCompatImageButton> = emptyList()
    private var outputSpinner: Spinner? = null
    private var inputSpinner: Spinner? = null
    private var mediaError: TextView? = null
    private var mediaAction: ((ActionCommand) -> Unit)? = null
    private val root = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    private val actionsContainer = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    private val devicesContainer = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }

    init {
        setBackgroundColor(color(R.color.ezwin_background))
        addView(root, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(actionsContainer)
        root.addView(devicesContainer, verticalParams(dp(16)))
    }

    fun updateLocalVolume(value: Int) {
        mediaSeekBar?.let { if (it.progress != value) it.progress = value }
        mediaPercent?.text = context.getString(R.string.media_volume_percent, value)
    }

    internal fun mediaSpinnersForTest(): Pair<Spinner?, Spinner?> = outputSpinner to inputSpinner

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
        outputSpinner?.let { configureSpinner(it, state.renderDevices, state.selectedRenderId, ready.mediaLoading || ready.outputDevicePending, "set_output_device") }
        inputSpinner?.let { configureSpinner(it, state.captureDevices, state.selectedCaptureId, ready.mediaLoading || ready.inputDevicePending, "set_input_device") }
        mediaError?.apply { text = state.error.orEmpty(); visibility = if (state.error.isNullOrBlank()) View.GONE else View.VISIBLE }
    }

    fun render(
        state: ControlUiState,
        onAction: (ActionCommand) -> Unit,
        onRevokeDevice: (String) -> Unit,
        onRenameDevice: (String, String) -> Unit,
        onBackToPairing: () -> Unit,
    ) {
        when (state) {
            ControlUiState.Loading -> renderActions(
                listOf(ActionPlugin("media", context.getString(R.string.media_title), "", "", emptyList())),
                state,
                onAction,
                onBackToPairing,
            )
            is ControlUiState.Error -> {
                actionsContainer.removeAllViews()
                actionsContainer.addView(emptyView(state.message))
                devicesContainer.removeAllViews()
            }
            is ControlUiState.Ready -> {
                renderActions(state.actions, state, onAction, onBackToPairing)
                renderDevices(state.devices, state.currentDeviceKey, onRevokeDevice, onRenameDevice)
            }
        }
    }

    internal fun renderActions(actions: List<ActionPlugin>, state: ControlUiState, onAction: (ActionCommand) -> Unit, onBack: () -> Unit) {
        actionsContainer.removeAllViews()
        actionsContainer.addView(secondaryButton(context.getString(R.string.main_back_to_pairing), onBack), iconButtonParams())
        if (actions.isEmpty()) {
            actionsContainer.addView(emptyView(context.getString(R.string.control_no_actions)), verticalParams(dp(12)))
            return
        }
        actions.forEach { plugin ->
            val card = if (plugin.name == "media") mediaCard(state as? ControlUiState.Ready, onAction) else pluginCard(plugin, onAction)
            actionsContainer.addView(card, verticalParams(dimen(R.dimen.media_card_spacing)).apply {
                leftMargin = dimen(R.dimen.media_card_horizontal_margin); rightMargin = dimen(R.dimen.media_card_horizontal_margin)
            })
        }
    }

    private fun mediaCard(ready: ControlUiState.Ready?, onAction: (ActionCommand) -> Unit): LinearLayout {
        val state = ready?.media
        val loading = ready == null || ready.mediaLoading
        val available = state?.available == true && !loading
        mediaAction = onAction
        return panel().apply {
            val header = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val cover = ImageView(context).apply {
                scaleType = ImageView.ScaleType.CENTER_CROP
                outlineProvider = object : ViewOutlineProvider() {
                    override fun getOutline(view: View, outline: android.graphics.Outline) {
                        outline.setRoundRect(0, 0, view.width, view.height, dp(14).toFloat())
                    }
                }
                clipToOutline = true
                setBackgroundColor(color(R.color.ezwin_panel_alt))
                val bitmap = ready?.artwork?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                if (bitmap == null) setImageResource(R.drawable.ic_album_placeholder_48) else setImageBitmap(bitmap)
                contentDescription = if (available) context.getString(
                    R.string.media_cover_description,
                    state?.title ?: context.getString(R.string.media_no_content),
                    state?.artist ?: context.getString(R.string.media_artist_unknown),
                ) else context.getString(R.string.media_cover_unavailable)
            }
            header.addView(cover, LinearLayout.LayoutParams(dimen(R.dimen.media_cover_size), dimen(R.dimen.media_cover_size)))
            val texts = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
            mediaTitle = singleLine(state?.title ?: if (loading) context.getString(R.string.media_loading) else context.getString(R.string.media_no_content), 16f, true)
            mediaArtist = singleLine(state?.artist ?: context.getString(R.string.media_artist_unknown), 14f, false)
            texts.addView(mediaTitle)
            texts.addView(mediaArtist, verticalParams(dp(6)))
            val status = when {
                loading -> context.getString(R.string.media_loading)
                !available -> context.getString(R.string.media_no_content)
                state?.playback == MediaPlayback.PLAYING -> context.getString(R.string.media_playing)
                state?.playback == MediaPlayback.PAUSED -> context.getString(R.string.media_paused)
                else -> context.getString(R.string.media_stopped)
            }
            mediaStatus = metaText(status)
            texts.addView(mediaStatus, verticalParams(dp(6)))
            header.addView(texts, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dimen(R.dimen.media_header_gap) })
            addView(header)

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
            outputSpinner = addDeviceSelector(R.drawable.ic_speaker_20, R.string.media_output_device, R.string.media_select_output, state?.renderDevices.orEmpty(), state?.selectedRenderId, loading || ready?.outputDevicePending == true, "set_output_device", onAction)
            inputSpinner = addDeviceSelector(R.drawable.ic_microphone_20, R.string.media_input_device, R.string.media_select_input, state?.captureDevices.orEmpty(), state?.selectedCaptureId, loading || ready?.inputDevicePending == true, "set_input_device", onAction)
            mediaError = metaText(state?.error.orEmpty()).apply { setTextColor(color(R.color.ezwin_error)); visibility = if (state?.error.isNullOrBlank()) View.GONE else View.VISIBLE }
            addView(mediaError, verticalParams(dp(12)))
        }
    }

    private fun LinearLayout.addDeviceSelector(icon: Int, label: Int, description: Int, endpoints: List<AudioEndpoint>, selectedId: String?, disabled: Boolean, command: String, onAction: (ActionCommand) -> Unit): Spinner {
        val title = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        title.addView(ImageView(context).apply { setImageResource(icon); importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }, LinearLayout.LayoutParams(dp(20), dp(20)))
        title.addView(bodyText(context.getString(label)), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dp(8) })
        addView(title, verticalParams(if (childCount > 6) dp(12) else 0))
        val spinner = Spinner(context)
        configureSpinner(spinner, endpoints, selectedId, disabled, command, description, onAction)
        addView(spinner, verticalParams(dp(6)))
        return spinner
    }

    private fun configureSpinner(spinner: Spinner, endpoints: List<AudioEndpoint>, selectedId: String?, disabled: Boolean, command: String, description: Int = if (command == "set_output_device") R.string.media_select_output else R.string.media_select_input, onAction: ((ActionCommand) -> Unit)? = mediaAction) {
        val options = if (endpoints.isEmpty()) {
            DeviceSelectorOptions(listOf(context.getString(if (disabled) R.string.media_devices_loading else R.string.media_no_devices)), listOf(null), 0)
        } else {
            deviceSelectorOptions(endpoints, selectedId, context.getString(R.string.media_choose_device))
        }
        val policy = DeviceSelectionGate(selectedId)
        spinner.adapter = ArrayAdapter(context, android.R.layout.simple_spinner_dropdown_item, options.labels)
        spinner.setBackgroundResource(R.drawable.ez_input)
        spinner.minimumHeight = dp(48)
        spinner.isEnabled = !disabled && endpoints.isNotEmpty()
        spinner.contentDescription = DeviceSelectorAccessibility(context.getString(description), "").controlDescription
        spinner.setSelection(options.selectedIndex, false)
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                val endpointId = options.endpointIds.getOrNull(position)
                endpointId?.let { policy.userSelection(it) }?.let { onAction?.invoke(mediaCommand(command, "endpoint_id", it)) }
                view?.contentDescription = DeviceSelectorAccessibility(spinner.contentDescription.toString(), options.labels[position]).optionDescription
            }
        }
        spinner.post { policy.finishProgrammaticUpdate() }
    }

    private fun mediaCommand(subAction: String, key: String? = null, value: Any? = null) = ActionCommand("media", buildMap { put("sub_action", subAction); if (key != null) put(key, value) })
    private fun mediaButton(icon: Int, description: Int, enabled: Boolean, click: () -> Unit) = AppCompatImageButton(context).apply { setImageResource(icon); setBackgroundResource(R.drawable.media_icon_button); contentDescription = context.getString(description); isEnabled = enabled; alpha = if (enabled) 1f else .38f; setOnClickListener { click() } }

    private fun pluginCard(plugin: ActionPlugin, onAction: (ActionCommand) -> Unit) = panel().apply {
        addView(singleLine(plugin.label, 15f, true))
        if (plugin.subActions.isEmpty()) addView(primaryButton(plugin.label) { onAction(ActionCommand(plugin.name)) }, verticalParams(dp(12))) else addView(GridLayout(context).apply {
            columnCount = 2
            plugin.subActions.forEach { sub -> addView(primaryButton(sub.label) { onAction(mediaCommandFor(plugin.name, sub.id)) }, gridParams()) }
        }, verticalParams(dp(12)))
    }
    private fun mediaCommandFor(plugin: String, sub: String) = ActionCommand(plugin, mapOf("sub_action" to sub))

    fun renderDevices(devices: List<DeviceInfo>, current: String?, revoke: (String) -> Unit, rename: (String, String) -> Unit) {
        devicesContainer.removeAllViews(); if (devices.isEmpty()) return
        devicesContainer.addView(secondaryButton(context.getString(if (devicesExpanded) R.string.control_devices_expanded else R.string.control_devices_collapsed, devices.size)) { devicesExpanded = !devicesExpanded; renderDevices(devices, current, revoke, rename) })
        if (devicesExpanded) devices.forEach { device -> devicesContainer.addView(panel().apply { addView(bodyText(device.name.ifBlank { device.key })); addView(secondaryButton(context.getString(R.string.control_rename_device)) { showRenameDialog(device, rename) }); addView(secondaryButton(context.getString(R.string.control_revoke_device, device.name)) { revoke(device.key) }) }, verticalParams(dp(8))) }
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
