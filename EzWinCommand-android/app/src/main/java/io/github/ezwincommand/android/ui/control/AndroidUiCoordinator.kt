package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.state.ConnectionRepository
import io.github.ezwincommand.android.state.RestoreResult

class AndroidUiCoordinator(
    private val connectionRepository: ConnectionRepository,
    private val createController: (String) -> ControlController,
) {
    var state: AndroidUiState = AndroidUiState.Main
        private set

    fun saveDraft(draft: MainDraft) {
        state = when (val current = state) {
            AndroidUiState.Main -> current
            is AndroidUiState.Control -> current.copy(draft = draft)
        }
    }

    suspend fun restoreSession(): AndroidUiEffect? {
        return when (val result = connectionRepository.restoreSession()) {
            is RestoreResult.Restored -> {
                state = AndroidUiState.Control(result.baseUrl)
                AndroidUiEffect.OpenControl(result.baseUrl)
            }
            is RestoreResult.InvalidSavedSession -> {
                connectionRepository.signOut()
                state = AndroidUiState.Main
                AndroidUiEffect.ShowMessage(result.message)
            }
            RestoreResult.NoSavedSession -> {
                state = AndroidUiState.Main
                null
            }
        }
    }

    fun openControl(baseUrl: String): ControlController {
        state = AndroidUiState.Control(baseUrl)
        return createController(baseUrl)
    }

    fun onAuthInvalid(): AndroidUiEffect {
        connectionRepository.signOut()
        state = AndroidUiState.Main
        return AndroidUiEffect.ReturnToMain
    }

    fun updateControlState(baseUrl: String, controlState: ControlUiState) {
        val draft = (state as? AndroidUiState.Control)?.draft ?: MainDraft()
        state = AndroidUiState.Control(baseUrl, controlState, draft)
    }
}
