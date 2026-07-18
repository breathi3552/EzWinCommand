package io.github.ezwincommand.android

import android.app.Dialog
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
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

    private fun serverButton(name: String, serverId: String, status: String, action: () -> Unit) = Button(this).apply {
        text = "$name · ${serverId.take(8)} · $status"
        isAllCaps = false
        setOnClickListener { action() }
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
        val dialog = Dialog(this)
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.ez_panel)
            setPadding(dp(32), dp(28), dp(32), dp(24))
        }
        content.addView(dialogTitle(getString(R.string.main_pair_dialog_title)))
        val codeInput = dialogInput(getString(R.string.main_pairing_code_hint)).apply {
            setText(binding.pairingCodeInput.text?.toString().orEmpty())
            inputType = InputType.TYPE_CLASS_TEXT
            filters = arrayOf(InputFilter.LengthFilter(4))
        }
        val nameInput = dialogInput(getString(R.string.main_device_name_hint)).apply {
            setText(binding.deviceNameInput.text?.toString().orEmpty().ifBlank { getString(R.string.main_device_default) })
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PERSON_NAME
        }
        content.addView(codeInput, verticalParams(12))
        content.addView(nameInput, verticalParams(12))
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        actions.addView(dialogButton(getString(R.string.main_pair_dialog_negative)) { dialog.dismiss() }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(12) })
        actions.addView(dialogButton(getString(R.string.main_pair_dialog_positive)) {
            val code = codeInput.text?.toString().orEmpty().trim()
            val name = nameInput.text?.toString().orEmpty().trim().ifBlank { getString(R.string.main_device_default) }
            binding.pairingCodeInput.setText(code)
            binding.deviceNameInput.setText(name)
            dialog.dismiss()
            pairWithInput(baseUrl, code, name)
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        content.addView(actions, verticalParams(16))
        dialog.setContentView(content)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.show()
        dialog.window?.setLayout((resources.displayMetrics.widthPixels * 0.9f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
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
