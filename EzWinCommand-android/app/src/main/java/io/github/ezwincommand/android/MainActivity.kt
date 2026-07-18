package io.github.ezwincommand.android

import android.app.Dialog
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.Editable
import android.text.InputFilter
import android.text.TextWatcher
import android.text.InputType
import android.text.TextUtils
import android.view.Gravity
import android.view.inputmethod.InputMethodManager
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import io.github.ezwincommand.android.databinding.ActivityMainBinding
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.network.DiscoveredServer
import io.github.ezwincommand.android.network.DiscoveryEvent
import io.github.ezwincommand.android.network.NsdDiscoveryClient
import io.github.ezwincommand.android.state.ConnectionCheckResult
import io.github.ezwincommand.android.state.ConnectionRepository
import io.github.ezwincommand.android.state.NormalizeResult
import io.github.ezwincommand.android.state.PairingResult
import io.github.ezwincommand.android.storage.KeystoreCipher
import io.github.ezwincommand.android.storage.ServerSessionStore
import io.github.ezwincommand.android.ui.control.ActionCommand
import io.github.ezwincommand.android.ui.control.AndroidUiCoordinator
import io.github.ezwincommand.android.ui.control.AndroidUiEffect
import io.github.ezwincommand.android.ui.control.AndroidUiState
import io.github.ezwincommand.android.ui.control.ControlController
import io.github.ezwincommand.android.ui.control.ControlScreen
import io.github.ezwincommand.android.ui.control.MediaConnectionController
import io.github.ezwincommand.android.ui.control.MediaVolumeActor
import io.github.ezwincommand.android.ui.control.withDevicePending
import io.github.ezwincommand.android.ui.control.mergeAuthoritativeMedia
import io.github.ezwincommand.android.ui.control.ControlPageGate
import io.github.ezwincommand.android.ui.control.mergeReadyWithMedia
import io.github.ezwincommand.android.ui.control.ControlUiState
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.net.URI

internal fun sanitizePairingCode(raw: CharSequence): String = raw.filter { it in '0'..'9' }.take(4).toString()

internal fun truncateDeviceName(raw: String, maxCodePoints: Int = 128): String {
    val trimmed = raw.trim()
    val count = trimmed.codePointCount(0, trimmed.length)
    if (count <= maxCodePoints) return trimmed
    return trimmed.substring(0, trimmed.offsetByCodePoints(0, maxCodePoints))
}

internal fun resolveReadableDeviceName(marketName: String?, manufacturer: String?, model: String?, fallback: String): String {
    marketName?.trim()?.takeIf(String::isNotEmpty)?.let { return it }
    val maker = manufacturer?.trim().orEmpty()
    val product = model?.trim().orEmpty()
    val buildName = when {
        maker.isEmpty() -> product
        product.isEmpty() -> maker
        maker.equals(product, ignoreCase = true) -> maker
        else -> "$maker $product"
    }
    return buildName.ifBlank { fallback }
}
class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val sessionStore: ServerSessionStore by lazy {
        ServerSessionStore(getSharedPreferences("ezwincommand", MODE_PRIVATE), KeystoreCipher())
    }
    private val connectionRepository by lazy { ConnectionRepository(sessionStore) }
    private val discoveryClient by lazy { NsdDiscoveryClient(applicationContext) }
    private var discoveredServers: List<DiscoveredServer> = emptyList()
    private val coordinator: AndroidUiCoordinator by lazy {
        AndroidUiCoordinator(connectionRepository) { serverId -> createController(serverId) }
    }
    private var activeController: ControlController? = null
    private var activeBaseUrl: String? = null
    private var hideTopMessageRunnable: Runnable? = null
    private var mediaConnection: MediaConnectionController? = null
    private var mediaVolumeActor: MediaVolumeActor? = null
    private var mediaLifecycleJob: Job? = null
    private var activeLoadJob: Job? = null
    private val controlPageGate = ControlPageGate()
    private var activeReadyState: ControlUiState.Ready? = null
    private var pairingDialogGeneration = 0L

    override fun onStart() {
        super.onStart()
        controlPageGate.onStarted { trackActivePending() }
    }

    private fun trackActivePending() {
        activeController?.trackAllPending(lifecycleScope) { result ->
            runOnUiThread { showTopMessage(if (result.success) result.message else errorMessage(result.message)) }
        }
    }

    override fun onStop() {
        pairingDialogGeneration += 1
        discoveryClient.stop()
        connectionRepository.cancelCurrent()
        activeController?.cancelTracking()
        controlPageGate.invalidate()
        super.onStop()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.pcPortInput.setText(AppConstants.DEFAULT_PORT.toString())
        binding.deviceNameInput.setText(getString(R.string.main_device_default))
        binding.testConnectionButton.setOnClickListener { testConnection() }
        binding.pairButton.setOnClickListener { pairDevice() }
        binding.refreshButton.setOnClickListener { refreshPairingPage() }
        binding.manualToggle.setOnClickListener {
            val expanded = binding.connectionCard.visibility != View.VISIBLE
            binding.connectionCard.visibility = if (expanded) View.VISIBLE else View.GONE
            binding.manualToggle.setText(if (expanded) R.string.main_manual_expanded else R.string.main_manual_collapsed)
        }
        binding.pairingCodeInput.inputType = InputType.TYPE_CLASS_NUMBER
        binding.connectionCard.visibility = View.GONE
        renderServerLists()

        lifecycleScope.launch {
            connectionRepository.migrateLegacy()
            renderEffect(coordinator.restoreSession())
            if (coordinator.state == AndroidUiState.Main) refreshPairingPage()
        }

    }

    private fun refreshPairingPage() {
        binding.scanStatusText.setText(R.string.main_scan_scanning)
        binding.refreshButton.isEnabled = false
        discoveryClient.scan { event ->
            runOnUiThread {
                when (event) {
                    is DiscoveryEvent.Updated -> { discoveredServers = event.servers; renderServerLists() }
                    is DiscoveryEvent.Finished -> { discoveredServers = event.servers; renderServerLists(); binding.scanStatusText.setText(R.string.main_scan_finished); binding.refreshButton.isEnabled = true }
                    is DiscoveryEvent.Unavailable -> { discoveredServers = emptyList(); renderServerLists(); binding.scanStatusText.text = event.message; binding.refreshButton.isEnabled = true }
                }
            }
        }
    }

    private fun renderServerLists() {
        val saved = connectionRepository.savedServers()
        val savedById = saved.associateBy { it.serverId }
        binding.nearbyList.removeAllViews()
        if (discoveredServers.isEmpty()) binding.nearbyList.addView(binding.nearbyEmptyText.also { (it.parent as? ViewGroup)?.removeView(it) })
        discoveredServers.forEach { server ->
            val known = savedById[server.serverId]
            binding.nearbyList.addView(serverButton(server.name, server.serverId, if (known?.needsRepair == true) getString(R.string.main_server_repair) else getString(R.string.main_server_online)) { connectFromList(server.baseUrl) })
        }
        binding.historyList.removeAllViews()
        if (saved.isEmpty()) binding.historyList.addView(binding.historyEmptyText.also { (it.parent as? ViewGroup)?.removeView(it) })
        saved.forEach { session ->
            val online = discoveredServers.firstOrNull { it.serverId == session.serverId }
            val status = when { session.needsRepair -> getString(R.string.main_server_repair); online != null -> getString(R.string.main_server_online); else -> getString(R.string.main_server_offline) }
            binding.historyList.addView(serverButton(session.deviceName.ifBlank { session.serverId }, session.serverId, status) { connectFromList(online?.baseUrl ?: session.baseUrl) })
        }
    }

    private fun serverButton(name: String, serverId: String, status: String, action: () -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.ez_input)
        setPadding(dp(16), dp(12), dp(16), dp(12))
        minimumHeight = dp(72)
        isClickable = true
        isFocusable = true
        contentDescription = "$name, $serverId, $status"
        setOnClickListener { action() }
        layoutParams = verticalParams(dp(8))

        addView(TextView(this@MainActivity).apply {
            text = name
            setTextColor(getColor(R.color.ezwin_text))
            textSize = 16f
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(TextView(this@MainActivity).apply {
                text = serverId.take(8)
                setTextColor(getColor(R.color.ezwin_text_muted))
                textSize = 13f
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(this@MainActivity).apply {
                text = status
                setTextColor(getColor(when (status) {
                    getString(R.string.main_server_online) -> R.color.ezwin_secondary
                    getString(R.string.main_server_repair) -> R.color.ezwin_warning
                    else -> R.color.ezwin_text_muted
                }))
                textSize = 13f
            })
        }, verticalParams(dp(4)))
    }

    private fun connectFromList(baseUrl: String) {
        populateBaseUrl(baseUrl)
        testConnection()
    }

    private fun testConnection() {
        val baseUrl = readBaseUrl() ?: return
        setInputsEnabled(false)
        showTopMessage(getString(R.string.main_status_checking))
        lifecycleScope.launch {
            when (val result = connectionRepository.testConnection(baseUrl)) {
                is ConnectionCheckResult.Reachable -> {
                    if (result.pairingId == null && result.savedSession != null) {
                        showTopMessage(getString(R.string.main_session_restored))
                        renderEffect(AndroidUiEffect.OpenControl(result.identity.serverId, result.baseUrl))
                    } else {
                        showTopMessage(getString(R.string.main_connection_success))
                        showPairingDialog(result.baseUrl)
                    }
                }
                is ConnectionCheckResult.Unreachable -> showTopMessage(errorMessage(result.message))
            }
            setInputsEnabled(true)
        }
    }

    private fun pairDevice() {
        val baseUrl = readBaseUrl() ?: return
        val pairingCode = binding.pairingCodeInput.text?.toString().orEmpty().trim()
        val deviceName = binding.deviceNameInput.text?.toString().orEmpty().trim().ifBlank { getString(R.string.main_device_default) }
        pairWithInput(baseUrl, pairingCode, deviceName)
    }

    private fun pairWithInput(baseUrl: String, pairingCode: String, deviceName: String) {
        if (pairingCode.isBlank()) {
            showTopMessage(errorMessage(getString(R.string.main_invalid_input)))
            return
        }
        setInputsEnabled(false)
        showTopMessage(getString(R.string.main_status_pairing))
        lifecycleScope.launch {
            when (val result = connectionRepository.pair(baseUrl, pairingCode, deviceName)) {
                is PairingResult.Paired -> {
                    showTopMessage(getString(R.string.main_pairing_success))
                    renderEffect(AndroidUiEffect.OpenControl(result.session.serverId, result.session.baseUrl))
                }
                PairingResult.UiInvalidated -> return@launch
                is PairingResult.Failed -> showTopMessage(errorMessage(result.message))
            }
            if (lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)) setInputsEnabled(true)
        }
    }

    private fun showPairingDialog(baseUrl: String) {
        val generation = ++pairingDialogGeneration
        val dialog = Dialog(this)
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.ez_panel)
            setPadding(dp(32), dp(28), dp(32), dp(24))
        }
        content.addView(dialogTitle(getString(R.string.main_pair_dialog_title)))
        val codeInput = pairingCodeInput()
        val codeCells = pairingCodeCells(codeInput)
        content.addView(codeCells.first, verticalParams(dp(16)))
        content.addView(TextView(this).apply {
            setText(R.string.main_device_name_label)
            setTextColor(getColor(R.color.ezwin_text_muted))
            textSize = 13f
        }, verticalParams(dp(18)))
        val nameViews = pairingNameViews(readableDeviceName(), codeInput)
        content.addView(nameViews.display, verticalParams(dp(6)))
        content.addView(nameViews.editor, verticalParams(dp(6)))
        val status = TextView(this).apply {
            setTextColor(getColor(R.color.ezwin_error))
            textSize = 13f
            visibility = View.GONE
        }
        content.addView(status, verticalParams(dp(8)))
        val cancel = dialogButton(getString(R.string.main_pair_dialog_negative)) { dialog.cancel() }
        content.addView(cancel, verticalParams(dp(18)))
        bindPairingDialog(dialog, generation, baseUrl, codeInput, codeCells.second, nameViews, status, cancel)
        dialog.setContentView(content)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.show()
        dialog.window?.setLayout((resources.displayMetrics.widthPixels * 0.9f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
        codeInput.post {
            if (pairingDialogGeneration == generation && dialog.isShowing) {
                codeInput.requestFocus()
                (getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager).showSoftInput(codeInput, InputMethodManager.SHOW_IMPLICIT)
            }
        }
    }

    private data class PairingNameViews(
        val display: LinearLayout,
        val editor: LinearLayout,
        val value: TextView,
        val input: EditText,
        val edit: ImageButton,
        val confirm: ImageButton,
    )

    private fun pairingCodeInput() = EditText(this).apply {
        id = View.generateViewId()
        inputType = InputType.TYPE_CLASS_NUMBER
        setTextColor(Color.TRANSPARENT)
        setHintTextColor(Color.TRANSPARENT)
        background = ColorDrawable(Color.TRANSPARENT)
        isCursorVisible = false
        alpha = 0.02f
        contentDescription = getString(R.string.main_pairing_code_accessibility)
        importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        isSingleLine = true
        filters = arrayOf(InputFilter.LengthFilter(16))
    }

    private fun pairingCodeCells(input: EditText): Pair<FrameLayout, Array<TextView>> {
        val cells = Array(4) {
            TextView(this).apply {
                gravity = Gravity.CENTER
                textSize = 22f
                setTextColor(getColor(R.color.ezwin_text))
                setBackgroundResource(R.drawable.ez_input)
                minimumHeight = dp(52)
                isClickable = true
                isFocusable = false
                setOnClickListener { if (isEnabled) input.requestFocus() }
            }
        }
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            contentDescription = getString(R.string.main_pairing_code_cells_description)
            cells.forEachIndexed { index, cell ->
                addView(cell, LinearLayout.LayoutParams(0, dp(52), 1f).apply { if (index > 0) leftMargin = dp(8) })
            }
        }
        return FrameLayout(this).apply {
            addView(row, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(input, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)))
        } to cells
    }

    private fun pairingNameViews(initialName: String, codeInput: EditText): PairingNameViews {
        val display = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val value = TextView(this).apply {
            text = initialName
            setTextColor(getColor(R.color.ezwin_text))
            textSize = 16f
            maxLines = 2
        }
        val edit = ImageButton(this).apply {
            id = View.generateViewId()
            setImageResource(R.drawable.ic_edit_24)
            setBackgroundColor(Color.TRANSPARENT)
            contentDescription = getString(R.string.main_device_name_edit)
            minimumWidth = dp(48)
            minimumHeight = dp(48)
        }
        display.addView(value, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        display.addView(edit, LinearLayout.LayoutParams(dp(48), dp(48)))
        val editor = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            visibility = View.GONE
        }
        val input = dialogInput(getString(R.string.main_device_name_hint)).apply {
            id = View.generateViewId()
            setText(initialName)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PERSON_NAME
            maxLines = 2
        }
        val confirm = ImageButton(this).apply {
            id = View.generateViewId()
            setImageResource(R.drawable.ic_check_24)
            setBackgroundColor(Color.TRANSPARENT)
            contentDescription = getString(R.string.main_device_name_confirm)
            minimumWidth = dp(40)
            minimumHeight = dp(40)
            setPadding(dp(8), dp(8), dp(8), dp(8))
        }
        editor.addView(input, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(4) })
        editor.addView(confirm, LinearLayout.LayoutParams(dp(40), dp(40)))
        edit.setOnClickListener {
            input.setText(value.text)
            input.setSelection(input.text?.length ?: 0)
            display.visibility = View.GONE
            editor.visibility = View.VISIBLE
            input.requestFocus()
        }
        confirm.setOnClickListener {
            val candidate = truncateDeviceName(input.text?.toString().orEmpty())
            if (candidate.isBlank()) Toast.makeText(this, R.string.main_device_name_blank, Toast.LENGTH_SHORT).show()
            else {
                value.text = candidate
                input.setText(candidate)
                editor.visibility = View.GONE
                display.visibility = View.VISIBLE
                codeInput.requestFocus()
            }
        }
        return PairingNameViews(display, editor, value, input, edit, confirm)
    }

    private fun readableDeviceName(): String {
        val marketName = runCatching { Settings.Global.getString(contentResolver, Settings.Global.DEVICE_NAME) }.getOrNull()
        return resolveReadableDeviceName(marketName, Build.MANUFACTURER, Build.MODEL, getString(R.string.main_device_default))
    }

    private fun bindPairingDialog(
        dialog: Dialog,
        generation: Long,
        baseUrl: String,
        codeInput: EditText,
        cells: Array<TextView>,
        names: PairingNameViews,
        status: TextView,
        cancel: Button,
    ) {
        var code = ""
        var submitting = false
        var armed = true
        var userRevision = 0L
        var rendering = false
        fun isCurrent() = pairingDialogGeneration == generation && dialog.isShowing && !isFinishing &&
            !(Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR1 && isDestroyed)
        fun renderCode() {
            cells.forEachIndexed { index, cell ->
                cell.text = code.getOrNull(index)?.toString().orEmpty()
                cell.alpha = if (submitting) 0.45f else 1f
            }
            codeInput.contentDescription = getString(R.string.main_pairing_code_progress, code.length)
        }
        fun renderSubmitting() {
            codeInput.isEnabled = !submitting
            cells.forEach { it.isEnabled = !submitting }
            names.edit.isEnabled = !submitting
            names.input.isEnabled = !submitting
            names.confirm.isEnabled = !submitting
            cancel.isEnabled = !submitting
            dialog.setCancelable(!submitting)
            dialog.setCanceledOnTouchOutside(false)
            if (submitting) {
                status.setTextColor(getColor(R.color.ezwin_text_muted))
                status.setText(R.string.main_status_pairing)
                status.visibility = View.VISIBLE
            }
            renderCode()
        }
        fun submitIfReady() {
            if (code.length != 4 || !armed || submitting || !isCurrent()) return
            submitting = true
            armed = false
            val submittedCode = code
            val submittedName = names.value.text.toString()
            val submittedRevision = userRevision
            renderSubmitting()
            lifecycleScope.launch {
                val result = connectionRepository.pair(baseUrl, submittedCode, submittedName)
                if (!isCurrent()) return@launch
                when (result) {
                    is PairingResult.Paired -> {
                        if (userRevision != submittedRevision) return@launch
                        pairingDialogGeneration += 1
                        dialog.dismiss()
                        showTopMessage(getString(R.string.main_pairing_success))
                        renderEffect(AndroidUiEffect.OpenControl(result.session.serverId, result.session.baseUrl))
                    }
                    PairingResult.UiInvalidated -> {
                        pairingDialogGeneration += 1
                        dialog.dismiss()
                    }
                    is PairingResult.Failed -> {
                        submitting = false
                        armed = false
                        status.setTextColor(getColor(R.color.ezwin_error))
                        status.text = errorMessage(result.message)
                        status.visibility = View.VISIBLE
                        renderSubmitting()
                        codeInput.requestFocus()
                    }
                }
            }
        }
        codeInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(editable: Editable?) {
                if (rendering) return
                val normalized = sanitizePairingCode(editable ?: "")
                if (editable?.toString() != normalized) {
                    rendering = true
                    codeInput.setText(normalized)
                    codeInput.setSelection(normalized.length)
                    rendering = false
                }
                if (normalized != code) {
                    code = normalized
                    userRevision += 1
                    armed = true
                    status.visibility = View.GONE
                }
                renderCode()
                submitIfReady()
            }
        })
        dialog.setOnCancelListener {
            if (pairingDialogGeneration == generation) {
                pairingDialogGeneration += 1
                connectionRepository.cancelCurrent()
            }
        }
        dialog.setOnDismissListener { if (pairingDialogGeneration == generation) pairingDialogGeneration += 1 }
        cancel.setOnClickListener { if (!submitting) dialog.cancel() }
    }

    private fun readBaseUrl(): String? {
        val address = binding.pcAddressInput.text?.toString().orEmpty()
        val port = binding.pcPortInput.text?.toString().orEmpty()
        return when (val result = connectionRepository.normalizeInputForAndroid(address, port)) {
            is NormalizeResult.Valid -> result.baseUrl
            is NormalizeResult.Invalid -> {
                showTopMessage(errorMessage(result.message))
                null
            }
        }
    }

    private suspend fun renderEffect(effect: AndroidUiEffect?) {
        when (effect) {
            null -> renderState()
            is AndroidUiEffect.ShowMessage -> {
                showMainScreen()
                showTopMessage(errorMessage(effect.message))
            }
            is AndroidUiEffect.OpenControl -> openControl(effect.serverId, effect.baseUrl)
            AndroidUiEffect.ReturnToMain -> showMainScreen()
        }
    }

    private fun renderState() {
        when (val state = coordinator.state) {
            AndroidUiState.Main -> showMainScreen()
            is AndroidUiState.Control -> openControl(state.serverId, state.baseUrl)
        }
    }

    private fun showMainScreen() {
        closeMediaSession()
        activeController?.close()
        activeController = null
        activeBaseUrl = null
        binding.pairingContainer.visibility = View.VISIBLE
        binding.titleText.visibility = View.VISIBLE
        binding.connectionCard.visibility = View.GONE
        binding.manualToggle.setText(R.string.main_manual_collapsed)
        binding.pairingCard.visibility = View.GONE
        binding.controlContainer.removeAllViews()
        binding.connectionStatusText.visibility = View.GONE
    }

    private fun closeMediaSession() {
        controlPageGate.invalidate()
        activeLoadJob?.cancel()
        activeLoadJob = null
        mediaConnection?.close()
        mediaConnection = null
        mediaVolumeActor?.close()
        mediaVolumeActor = null
        mediaLifecycleJob?.cancel()
        mediaLifecycleJob = null
    }

    private fun openControl(serverId: String, baseUrl: String) {
        closeMediaSession()
        activeController?.close()
        binding.pairingContainer.visibility = View.GONE
        binding.titleText.visibility = View.GONE
        val screen = ControlScreen(this)
        binding.connectionCard.visibility = View.GONE
        binding.pairingCard.visibility = View.GONE
        binding.controlContainer.removeAllViews()
        binding.controlContainer.addView(screen)
        val controller = createController(serverId)
        activeController = controller
        activeBaseUrl = baseUrl
        val pageTicket = controlPageGate.begin(controller, baseUrl)
        activeLoadJob = lifecycleScope.launch {
            var currentState = controller.load()
            if (!controlPageGate.afterLoad(pageTicket, binding.controlContainer.indexOfChild(screen) >= 0) { trackActivePending() }) return@launch
            coordinator.updateControlState(serverId, baseUrl, currentState)
            fun redraw(updated: ControlUiState) {
                currentState = updated
                activeReadyState = updated as? ControlUiState.Ready
                coordinator.updateControlState(serverId, baseUrl, updated)
                renderControl(screen, controller, serverId, baseUrl, updated)
            }
            renderControl(screen, controller, serverId, baseUrl, currentState)
            activeReadyState = currentState as? ControlUiState.Ready
            val initialReady = currentState as? ControlUiState.Ready
            if (initialReady != null) {
                mediaLifecycleJob = lifecycleScope.launch {
                    repeatOnLifecycle(Lifecycle.State.STARTED) {
                        var latestAuthoritative = initialReady.media
                        lateinit var volumeActor: MediaVolumeActor
                        volumeActor = MediaVolumeActor(
                            scope = this,
                            execute = {
                                controller.sendMediaAction("set_volume", it).also { mediaConnection?.refresh() }
                            },
                            onLocalValue = screen::updateLocalVolume,
                            onConfirmed = { },
                            onFailure = { confirmed, message ->
                                screen.updateLocalVolume(confirmed)
                                val ready = activeReadyState ?: currentState as? ControlUiState.Ready ?: return@MediaVolumeActor
                                redraw(ready.copy(media = ready.media.copy(volume = confirmed, error = message)))
                            },
                            onIdle = {
                                val ready = activeReadyState ?: currentState as? ControlUiState.Ready ?: return@MediaVolumeActor
                                redraw(ready.copy(media = latestAuthoritative))
                            },
                        )
                        mediaVolumeActor = volumeActor
                        val connection = MediaConnectionController(
                            apiClient = controller.apiClient,
                            baseUrl = baseUrl,
                            scope = this,
                            onState = { media ->
                                val ready = activeReadyState ?: currentState as? ControlUiState.Ready ?: return@MediaConnectionController
                                latestAuthoritative = media
                                volumeActor.updateConfirmed(media.volume)
                                val busy = volumeActor.isBusy()
                                val updated = mergeReadyWithMedia(ready, media, busy)
                                activeReadyState = updated
                                if (!busy) redraw(updated) else {
                                    currentState = updated
                                    coordinator.updateControlState(serverId, baseUrl, updated)
                                    screen.updateMediaStateExcludingVolume(updated)
                                }
                            },
                            onArtwork = { _, bytes ->
                                val ready = activeReadyState ?: currentState as? ControlUiState.Ready ?: return@MediaConnectionController
                                redraw(ready.copy(artwork = bytes))
                            },
                            onError = { message ->
                                val ready = activeReadyState ?: currentState as? ControlUiState.Ready ?: return@MediaConnectionController
                                redraw(ready.copy(media = ready.media.copy(error = message), mediaLoading = false))
                            },
                            onAuthInvalid = { lifecycleScope.launch { renderEffect(coordinator.onAuthInvalid(serverId)) } },
                        )
                        mediaConnection = connection
                        connection.start(controller)
                        try {
                            kotlinx.coroutines.awaitCancellation()
                        } finally {
                            connection.close()
                            volumeActor.close()
                            if (mediaConnection === connection) mediaConnection = null
                            if (mediaVolumeActor === volumeActor) mediaVolumeActor = null
                        }
                    }
                }
            }
        }
        activeLoadJob?.invokeOnCompletion { if (activeLoadJob?.isCompleted == true) activeLoadJob = null }
    }

    private fun renderControl(
        screen: ControlScreen,
        controller: ControlController,
        serverId: String,
        baseUrl: String,
        controlState: ControlUiState,
    ) {
        lateinit var actionInvoker: (ActionCommand) -> Unit
        lateinit var revokeInvoker: (String) -> Unit
        lateinit var renameInvoker: (String, String) -> Unit
        actionInvoker = { command ->
            lifecycleScope.launch {
                val subAction = command.params["sub_action"] as? String
                if (command.action == "media" && subAction == "set_volume") {
                    val value = command.params["volume"] as Int
                    if (command.params["finish"] == true) mediaVolumeActor?.finishGesture(value) else mediaVolumeActor?.submitVolume(value)
                    return@launch
                }
                val result = if (command.action == "media" && subAction != null) {
                    val value = command.params["endpoint_id"]
                    val isDeviceCommand = subAction == "set_output_device" || subAction == "set_input_device"
                    val before = activeReadyState
                    if (isDeviceCommand && before != null) {
                        val pending = before.withDevicePending(subAction, true)
                        activeReadyState = pending
                        coordinator.updateControlState(serverId, baseUrl, pending)
                        screen.updateMediaStateExcludingVolume(pending)
                    }
                    try {
                        controller.sendMediaAction(subAction, value).also { mediaConnection?.refresh() }
                    } finally {
                        if (isDeviceCommand) {
                            val current = activeReadyState ?: before
                            if (current != null && activeController === controller && activeBaseUrl == baseUrl) {
                                val cleared = current.withDevicePending(subAction, false)
                                activeReadyState = cleared
                                coordinator.updateControlState(serverId, baseUrl, cleared)
                                screen.updateMediaStateExcludingVolume(cleared)
                            }
                        }
                    }
                } else {
                    controller.sendAction(command)
                }
                showTopMessage(screen.showResult(result))
                if (result.commandId != null && result.status != "succeeded" && result.status != "failed") {
                    controller.trackPending(command, lifecycleScope) { tracked -> runOnUiThread { showTopMessage(if (tracked.success) tracked.message else errorMessage(tracked.message)) } }
                }
                if (!result.success) showTopMessage(errorMessage(result.message))
            }
        }
        revokeInvoker = { value ->
            lifecycleScope.launch {
                val revoked = controller.revokeDevice(value)
                if (!revoked) {
                    showTopMessage(errorMessage(getString(R.string.control_revoke_failed)))
                    return@launch
                }
                if (value == activeReadyState?.currentDeviceKey) {
                    connectionRepository.removeSession(serverId)
                    showTopMessage(getString(R.string.control_revoke_success))
                    returnToPairing(baseUrl)
                    return@launch
                }
                showTopMessage(getString(R.string.control_revoke_success))
                val refreshed = controller.load()
                coordinator.updateControlState(serverId, baseUrl, refreshed)
                screen.render(refreshed, actionInvoker, revokeInvoker, renameInvoker, { returnToPairing(baseUrl) }, { mediaConnection?.refresh() })
            }
        }
        renameInvoker = { value, name ->
            lifecycleScope.launch {
                val renamed = controller.renameDevice(value, name)
                showTopMessage(if (renamed) getString(R.string.control_rename_device_success) else errorMessage(getString(R.string.control_rename_device_failed)))
                val refreshed = controller.load()
                coordinator.updateControlState(serverId, baseUrl, refreshed)
                screen.render(refreshed, actionInvoker, revokeInvoker, renameInvoker, { returnToPairing(baseUrl) }, { mediaConnection?.refresh() })
            }
        }
        screen.render(controlState, actionInvoker, revokeInvoker, renameInvoker, { returnToPairing(baseUrl) }, { mediaConnection?.refresh() })
    }

    private fun returnToPairing(baseUrl: String) {
        closeMediaSession()
        activeController?.close()
        activeController = null
        activeBaseUrl = null
        binding.pairingContainer.visibility = View.VISIBLE
        binding.titleText.visibility = View.VISIBLE
        binding.controlContainer.removeAllViews()
        binding.connectionCard.visibility = View.VISIBLE
        populateBaseUrl(baseUrl)
        showTopMessage(getString(R.string.main_connection_success))
    }

    private fun populateBaseUrl(baseUrl: String) {
        val uri = try { URI(baseUrl) } catch (_: Throwable) { return }
        binding.pcAddressInput.setText(uri.host.orEmpty())
        binding.pcPortInput.setText(if (uri.port == -1) AppConstants.DEFAULT_PORT.toString() else uri.port.toString())
    }

    private fun setInputsEnabled(enabled: Boolean) {
        binding.pcAddressInput.isEnabled = enabled
        binding.pcPortInput.isEnabled = enabled
        binding.pairingCodeInput.isEnabled = enabled
        binding.deviceNameInput.isEnabled = enabled
        binding.testConnectionButton.isEnabled = enabled
        binding.pairButton.isEnabled = enabled
    }


    private fun showTopMessage(message: String) {
        hideTopMessageRunnable?.let { binding.connectionStatusText.removeCallbacks(it) }
        binding.connectionStatusText.animate().cancel()
        binding.connectionStatusText.text = message
        binding.connectionStatusText.visibility = View.VISIBLE
        binding.connectionStatusText.alpha = 0f
        binding.connectionStatusText.translationY = -binding.connectionStatusText.height.toFloat().coerceAtLeast(dp(80).toFloat())
        binding.connectionStatusText.animate()
            .alpha(1f)
            .translationY(0f)
            .setDuration(180L)
            .withEndAction {
                val hideRunnable = Runnable {
                    binding.connectionStatusText.animate()
                        .alpha(0f)
                        .translationY(-binding.connectionStatusText.height.toFloat().coerceAtLeast(dp(80).toFloat()))
                        .setDuration(220L)
                        .withEndAction { binding.connectionStatusText.visibility = View.GONE }
                        .start()
                }
                hideTopMessageRunnable = hideRunnable
                binding.connectionStatusText.postDelayed(hideRunnable, 2600L)
            }
            .start()
    }

    private fun dialogTitle(text: String): TextView = TextView(this).apply {
        this.text = text
        setTextColor(getColor(R.color.ezwin_text))
        textSize = 18f
        setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun dialogInput(hintText: String): EditText = EditText(this).apply {
        hint = hintText
        setTextColor(getColor(R.color.ezwin_text))
        setHintTextColor(getColor(R.color.ezwin_text_muted))
        setBackgroundResource(R.drawable.ez_input)
        minHeight = 48
        setPadding(24, 12, 24, 12)
    }

    private fun dialogButton(text: String, onClick: () -> Unit): Button = Button(this).apply {
        this.text = text
        isAllCaps = false
        setTextColor(getColor(R.color.ezwin_text))
        setBackgroundResource(R.drawable.ez_button_primary)
        setOnClickListener { onClick() }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun verticalParams(top: Int): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = top }
    }

    private fun errorMessage(message: String): String {
        return if (message.startsWith(getString(R.string.main_error_prefix))) {
            message
        } else {
            getString(R.string.main_error_prefix) + message
        }
    }

    override fun onDestroy() {
        discoveryClient.close()
        closeMediaSession()
        activeController?.close()
        activeController = null
        super.onDestroy()
    }

    private fun createController(serverId: String): ControlController {
        val session = connectionRepository.session(serverId) ?: error("会话不存在")
        val apiClient = EzApiClient(session.baseUrl, { connectionRepository.deviceKey(serverId) }, timeoutMillis = 5_000)
        val pendingStore = io.github.ezwincommand.android.storage.PendingCommandStore(
            getSharedPreferences("ezwincommand_pending", MODE_PRIVATE),
            serverId,
            session.credentialVersion,
        )
        return ControlController(apiClient, currentDeviceKeyProvider = { connectionRepository.deviceKey(serverId) }, onAuthInvalid = {
            lifecycleScope.launch {
                renderEffect(coordinator.onAuthInvalid(serverId))
                showTopMessage(errorMessage(getString(R.string.main_restore_failed)))
            }
        }, pendingStore = pendingStore)
    }
}
