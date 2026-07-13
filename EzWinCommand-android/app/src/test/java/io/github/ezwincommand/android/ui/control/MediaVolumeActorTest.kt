package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class MediaVolumeActorTest {
    @Test
    fun `single in flight latest wins and final gesture is delivered`() = runTest {
        val starts = mutableListOf<Pair<Int, Long>>()
        val firstGate = CompletableDeferred<Unit>()
        var calls = 0
        val actor = MediaVolumeActor(
            scope = this,
            execute = { value ->
                starts += value to testScheduler.currentTime
                if (calls++ == 0) firstGate.await()
                CommandResult(true, "ok", emptyMap())
            },
            onLocalValue = {},
            onConfirmed = {},
            onFailure = { _, _ -> },
            nowMillis = { testScheduler.currentTime },
        )
        actor.submitVolume(10)
        testScheduler.runCurrent()
        actor.submitVolume(20)
        actor.submitVolume(30)
        actor.finishGesture(40)
        firstGate.complete(Unit)
        advanceUntilIdle()
        assertEquals(listOf(10, 40), starts.map { it.first })
        assertTrue(starts[1].second - starts[0].second >= 100L)
    }

    @Test
    fun `failure clears pending and rolls back confirmed value`() = runTest {
        var rollback = -1
        var observedError = ""
        var idleCalls = 0
        val actor = MediaVolumeActor(
            scope = this,
            execute = { CommandResult(false, "失败", emptyMap()) },
            onLocalValue = {},
            onConfirmed = {},
            onFailure = { confirmed, message -> rollback = confirmed; observedError = message },
            onIdle = { idleCalls++ },
            nowMillis = { testScheduler.currentTime },
        )
        actor.updateConfirmed(37)
        actor.submitVolume(80)
        advanceUntilIdle()
        assertEquals(37, rollback)
        assertEquals("失败", observedError)
        assertEquals(0, idleCalls)
    }
}
