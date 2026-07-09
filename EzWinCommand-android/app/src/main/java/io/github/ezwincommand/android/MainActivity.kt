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
import io.github.ezwincommand.android.databinding.ActivityMainBinding
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.state.ConnectionCheckResult
import io.github.ezwincommand.android.state.ConnectionRepository
import io.github.ezwincommand.android.state.NormalizeResult
import io.github.ezwincommand.android.state.PairingResult
import io.github.ezwincommand.android.storage.DeviceKeyStore
import io.github.ezwincommand.android.storage.SharedPreferencesDeviceKeyStore
import io.github.ezwincommand.android.ui.control.ActionCommand
import io.github.ezwincommand.android.ui.control.AndroidUiCoordinator
import io.github.ezwincommand.android.ui.control.AndroidUiEffect
import io.github.ezwincommand.android.ui.control.AndroidUiState
import io.github.ezwincommand.android.ui.control.ControlController
import io.github.ezwincommand.android.ui.control.ControlScreen
import io.github.ezwincommand.android.ui.control.ControlUiState
import kotlinx.coroutines.launch
import java.net.URI

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val deviceKeyStore: DeviceKeyStore by lazy {
        SharedPreferencesDeviceKeyStore(getSharedPreferences("ezwincommand", MODE_PRIVATE))
    }
    private val connectionRepository by lazy { ConnectionRepository(deviceKeyStore) }
    private val coordinator: AndroidUiCoordinator by lazy {
        AndroidUiCoordinator(connectionRepository) { baseUrl -> createController(baseUrl) }
    }
    private var hideTopMessageRunnable: Runnable? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.pcPortInput.setText(AppConstants.DEFAULT_PORT.toString())
        binding.deviceNameInput.setText(getString(R.string.main_device_default))
        binding.testConnectionButton.setOnClickListener { testConnection() }
        binding.pairButton.setOnClickListener { pairDevice() }
        binding.pairingCard.visibility = View.GONE
        binding.connectionStatusText.visibility = View.GONE

        lifecycleScope.launch {
            setInputsEnabled(false)
            showTopMessage(getString(R.string.main_status_restoring))
            renderEffect(coordinator.restoreSession())
            setInputsEnabled(true)
        }
        renderState()
    }

    private fun testConnection() {
        val baseUrl = readBaseUrl() ?: return
        setInputsEnabled(false)
        showTopMessage(getString(R.string.main_status_checking))
        lifecycleScope.launch {
            when (val result = connectionRepository.testConnection(baseUrl)) {
                is ConnectionCheckResult.Reachable -> {
                    val savedBaseUrl = deviceKeyStore.getBaseUrl()?.trim().orEmpty()
                    val savedKey = deviceKeyStore.getDeviceKey()?.trim().orEmpty()
                    if (savedBaseUrl == result.baseUrl && savedKey.isNotEmpty()) {
                        showTopMessage(getString(R.string.main_session_restored))
                        renderEffect(AndroidUiEffect.OpenControl(result.baseUrl))
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
                    renderEffect(AndroidUiEffect.OpenControl(result.baseUrl))
                }
                is PairingResult.Failed -> showTopMessage(errorMessage(result.message))
            }
            setInputsEnabled(true)
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
            is AndroidUiEffect.OpenControl -> openControl(effect.baseUrl)
            AndroidUiEffect.ReturnToMain -> showMainScreen()
        }
    }

    private fun renderState() {
        when (val state = coordinator.state) {
            AndroidUiState.Main -> showMainScreen()
            is AndroidUiState.Control -> openControl(state.baseUrl)
        }
    }

    private fun showMainScreen() {
        binding.titleText.visibility = View.VISIBLE
        binding.connectionCard.visibility = View.VISIBLE
        binding.pairingCard.visibility = View.GONE
        binding.controlContainer.removeAllViews()
        binding.connectionStatusText.visibility = View.GONE
    }

    private fun openControl(baseUrl: String) {
        binding.titleText.visibility = View.GONE
        val screen = ControlScreen(this)
        binding.connectionCard.visibility = View.GONE
        binding.pairingCard.visibility = View.GONE
        binding.controlContainer.removeAllViews()
        binding.controlContainer.addView(screen)
        lifecycleScope.launch {
            val controller = createController(baseUrl)
            val controlState = controller.load()
            coordinator.updateControlState(baseUrl, controlState)
            renderControl(screen, controller, baseUrl, controlState)
        }
    }

    private fun renderControl(
        screen: ControlScreen,
        controller: ControlController,
        baseUrl: String,
        controlState: ControlUiState,
    ) {
        lateinit var actionInvoker: (ActionCommand) -> Unit
        lateinit var revokeInvoker: (String) -> Unit
        lateinit var renameInvoker: (String, String) -> Unit
        actionInvoker = { command ->
            lifecycleScope.launch {
                val result = controller.sendAction(command)
                showTopMessage(screen.showResult(result))
                if (!result.success) {
                    screen.render(ControlUiState.Error(result.message, authInvalid = false), actionInvoker, revokeInvoker, renameInvoker) { returnToPairing(baseUrl) }
                }
            }
        }
        revokeInvoker = { value ->
            lifecycleScope.launch {
                val revoked = controller.revokeDevice(value)
                showTopMessage(if (revoked) getString(R.string.control_revoke_success) else errorMessage(getString(R.string.control_revoke_failed)))
                val refreshed = controller.load()
                coordinator.updateControlState(baseUrl, refreshed)
                screen.render(refreshed, actionInvoker, revokeInvoker, renameInvoker) { returnToPairing(baseUrl) }
            }
        }
        renameInvoker = { value, name ->
            lifecycleScope.launch {
                val renamed = controller.renameDevice(value, name)
                showTopMessage(if (renamed) getString(R.string.control_rename_device_success) else errorMessage(getString(R.string.control_rename_device_failed)))
                val refreshed = controller.load()
                coordinator.updateControlState(baseUrl, refreshed)
                screen.render(refreshed, actionInvoker, revokeInvoker, renameInvoker) { returnToPairing(baseUrl) }
            }
        }
        screen.render(controlState, actionInvoker, revokeInvoker, renameInvoker) { returnToPairing(baseUrl) }
    }

    private fun returnToPairing(baseUrl: String) {
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

    private fun createController(baseUrl: String): ControlController {
        val apiClient = EzApiClient(baseUrl, { deviceKeyStore.getDeviceKey() }, timeoutMillis = 5_000)
        return ControlController(apiClient, currentDeviceKeyProvider = { deviceKeyStore.getDeviceKey() }) {
            lifecycleScope.launch {
                renderEffect(coordinator.onAuthInvalid())
                showTopMessage(errorMessage(getString(R.string.main_restore_failed)))
            }
        }
    }
}
