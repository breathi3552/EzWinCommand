package io.github.ezwincommand.android.ui.control

internal class ControlPageGate {
    data class Ticket internal constructor(val generation: Long, val controller: Any, val baseUrl: String)

    private var generation = 0L
    private var activeController: Any? = null
    private var activeBaseUrl: String? = null
    private var initialTrackingStarted = false

    fun begin(controller: Any, baseUrl: String): Ticket {
        generation++
        activeController = controller
        activeBaseUrl = baseUrl
        initialTrackingStarted = false
        return Ticket(generation, controller, baseUrl)
    }

    fun invalidate() {
        generation++
        activeController = null
        activeBaseUrl = null
        initialTrackingStarted = false
    }

    fun afterLoad(ticket: Ticket, pageAttached: Boolean, startTracking: () -> Unit): Boolean {
        if (!isCurrent(ticket, pageAttached)) return false
        if (!initialTrackingStarted) {
            initialTrackingStarted = true
            startTracking()
        }
        return true
    }

    fun onStarted(startTracking: () -> Unit) {
        if (initialTrackingStarted && activeController != null) startTracking()
    }

    private fun isCurrent(ticket: Ticket, pageAttached: Boolean): Boolean =
        pageAttached && ticket.generation == generation && ticket.controller === activeController && ticket.baseUrl == activeBaseUrl
}
