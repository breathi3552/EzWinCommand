package io.github.ezwincommand.android.ui.control

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Test

class MediaControlPageGateTest {
    @Test
    fun `tracking is zero before load gate and exactly once after current gate`() {
        val gate = ControlPageGate()
        val controller = Any()
        val ticket = gate.begin(controller, "server-a")
        var tracks = 0
        gate.onStarted { tracks++ }
        assertEquals(0, tracks)
        assertTrue(gate.afterLoad(ticket, pageAttached = true) { tracks++ })
        assertEquals(1, tracks)
        gate.afterLoad(ticket, pageAttached = true) { tracks++ }
        assertEquals(1, tracks)
    }

    @Test
    fun `old generation and stopped page never start tracking`() {
        val gate = ControlPageGate()
        val old = gate.begin(Any(), "server-a")
        gate.begin(Any(), "server-b")
        var tracks = 0
        assertFalse(gate.afterLoad(old, pageAttached = true) { tracks++ })
        gate.invalidate()
        gate.onStarted { tracks++ }
        assertEquals(0, tracks)
    }

    @Test
    fun `detached page fails gate without tracking`() {
        val gate = ControlPageGate()
        val ticket = gate.begin(Any(), "server-a")
        var tracks = 0
        assertFalse(gate.afterLoad(ticket, pageAttached = false) { tracks++ })
        assertEquals(0, tracks)
    }
}
