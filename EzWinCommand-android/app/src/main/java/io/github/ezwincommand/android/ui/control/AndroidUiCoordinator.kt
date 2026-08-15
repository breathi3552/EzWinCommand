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

    suspend fun restoreSession(): AndroidUiEffect? = when (val result = connectionRepository.restoreSession()) {
        is RestoreResult.Restored -> {
            state = AndroidUiState.Control(result.session.serverId, result.session.baseUrl)
            AndroidUiEffect.OpenControl(result.session.serverId, result.session.baseUrl)
        }
        is RestoreResult.InvalidSavedSession -> {
            state = AndroidUiState.Main
            AndroidUiEffect.ShowMessage(result.message)
        }
        RestoreResult.NoSavedSession -> { state = AndroidUiState.Main; null }
    }

    fun openControl(serverId: String, baseUrl: String): ControlController {
        state = AndroidUiState.Control(serverId, baseUrl)
        return createController(serverId)
    }

    fun returnToMain() {
        state = AndroidUiState.Main
    }

    fun updateControlState(serverId: String, baseUrl: String, controlState: ControlUiState) {
        val draft = (state as? AndroidUiState.Control)?.draft ?: MainDraft()
        state = AndroidUiState.Control(serverId, baseUrl, controlState, draft)
    }
}
