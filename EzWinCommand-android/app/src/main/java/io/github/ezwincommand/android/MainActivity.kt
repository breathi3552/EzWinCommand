package io.github.ezwincommand.android

import android.os.Bundle
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

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val deviceKeyStore: DeviceKeyStore by lazy {
        SharedPreferencesDeviceKeyStore(getSharedPreferences("ezwincommand", MODE_PRIVATE))
    }
    private val connectionRepository by lazy { ConnectionRepository(deviceKeyStore) }
    private val coordinator: AndroidUiCoordinator by lazy {
        AndroidUiCoordinator(connectionRepository) { baseUrl -> createController(baseUrl) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.pcPortInput.setText(AppConstants.DEFAULT_PORT.toString())
        binding.deviceNameInput.setText(getString(R.string.main_device_default))
        binding.testConnectionButton.setOnClickListener { testConnection() }
        binding.pairButton.setOnClickListener { pairDevice() }

        lifecycleScope.launch {
            setInputsEnabled(false)
            setStatus(getString(R.string.main_status_restoring))
            renderEffect(coordinator.restoreSession())
            setInputsEnabled(true)
        }
        renderState()
    }

    private fun testConnection() {
        val baseUrl = readBaseUrl() ?: return
        setInputsEnabled(false)
        setStatus(getString(R.string.main_status_checking))
        lifecycleScope.launch {
            val result = connectionRepository.testConnection(baseUrl)
            setStatus(
                when (result) {
                    is ConnectionCheckResult.Reachable -> getString(R.string.main_connection_success)
                    is ConnectionCheckResult.Unreachable -> errorMessage(result.message)
                },
            )
            setInputsEnabled(true)
        }
    }

    private fun pairDevice() {
        val baseUrl = readBaseUrl() ?: return
        val pairingCode = binding.pairingCodeInput.text?.toString().orEmpty().trim()
        val deviceName = binding.deviceNameInput.text?.toString().orEmpty().trim().ifBlank { getString(R.string.main_device_default) }
        if (pairingCode.isBlank()) {
            setStatus(errorMessage(getString(R.string.main_invalid_input)))
            return
        }
        setInputsEnabled(false)
        setStatus(getString(R.string.main_status_pairing))
        lifecycleScope.launch {
            when (val result = connectionRepository.pair(baseUrl, pairingCode, deviceName)) {
                is PairingResult.Paired -> {
                    setStatus(getString(R.string.main_pairing_success))
                    renderEffect(AndroidUiEffect.OpenControl(result.baseUrl))
                }
                is PairingResult.Failed -> setStatus(errorMessage(result.message))
            }
            setInputsEnabled(true)
        }
    }

    private fun readBaseUrl(): String? {
        val address = binding.pcAddressInput.text?.toString().orEmpty()
        val port = binding.pcPortInput.text?.toString().orEmpty()
        return when (val result = connectionRepository.normalizeInputForAndroid(address, port)) {
            is NormalizeResult.Valid -> result.baseUrl
            is NormalizeResult.Invalid -> {
                setStatus(errorMessage(result.message))
                null
            }
        }
    }

    private suspend fun renderEffect(effect: AndroidUiEffect?) {
        when (effect) {
            null -> renderState()
            is AndroidUiEffect.ShowMessage -> {
                showMainScreen()
                setStatus(errorMessage(effect.message))
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
        binding.controlContainer.removeAllViews()
        binding.connectionStatusText.text = getString(R.string.main_status_idle)
    }

    private fun openControl(baseUrl: String) {
        val screen = ControlScreen(this)
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
        actionInvoker = { command ->
            lifecycleScope.launch {
                val result = controller.sendAction(command)
                setStatus(screen.showResult(result))
                if (!result.success) {
                    screen.render(ControlUiState.Error(result.message, authInvalid = false), actionInvoker, revokeInvoker)
                }
            }
        }
        revokeInvoker = { deviceKey ->
            lifecycleScope.launch {
                val revoked = controller.revokeDevice(deviceKey)
                setStatus(
                    if (revoked) {
                        getString(R.string.control_revoke_success)
                    } else {
                        errorMessage(getString(R.string.control_revoke_failed))
                    },
                )
                val refreshed = controller.load()
                coordinator.updateControlState(baseUrl, refreshed)
                screen.render(refreshed, actionInvoker, revokeInvoker)
            }
        }
        screen.render(controlState, actionInvoker, revokeInvoker)
    }

    private fun setInputsEnabled(enabled: Boolean) {
        binding.pcAddressInput.isEnabled = enabled
        binding.pcPortInput.isEnabled = enabled
        binding.pairingCodeInput.isEnabled = enabled
        binding.deviceNameInput.isEnabled = enabled
        binding.testConnectionButton.isEnabled = enabled
        binding.pairButton.isEnabled = enabled
    }

    private fun setStatus(message: String) {
        binding.connectionStatusText.text = message
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
        return ControlController(apiClient) {
            lifecycleScope.launch {
                renderEffect(coordinator.onAuthInvalid())
                setStatus(errorMessage(getString(R.string.main_restore_failed)))
            }
        }
    }
}
