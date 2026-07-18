package io.github.ezwincommand.android.network

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.util.Log
import java.io.Closeable
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

data class DiscoveredServer(val serverId: String, val name: String, val baseUrl: String)

sealed interface DiscoveryEvent {
    data class Updated(val servers: List<DiscoveredServer>) : DiscoveryEvent
    data class Finished(val servers: List<DiscoveredServer>) : DiscoveryEvent
    data class Unavailable(val message: String) : DiscoveryEvent
}

/** 单 generation 的 Android NSD 扫描器。旧回调均以 generation 门丢弃。 */
class NsdDiscoveryClient(
    context: Context,
    private val clientFactory: (String) -> EzApiClient = { EzApiClient(it, { null }, 3_000) },
) : Closeable {
    private val appContext = context.applicationContext
    private val nsd = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val wifi = appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val generation = AtomicLong(0)
    private val identitySlots = Semaphore(4)
    private var listener: NsdManager.DiscoveryListener? = null
    private var lock: WifiManager.MulticastLock? = null
    private var deadline: Job? = null
    private val resolveQueue = ArrayDeque<NsdServiceInfo>()
    private var resolving = false
    private var callback: ((DiscoveryEvent) -> Unit)? = null
    private val found = linkedMapOf<String, DiscoveredServer>()
    private var foundCallbacks = 0
    private var resolveFailures = 0
    private var resolvedCallbacks = 0
    private var identitySuccesses = 0
    private var identityFailures = 0

    @Synchronized
    fun scan(onEvent: (DiscoveryEvent) -> Unit) {
        stopLocked(false)
        val current = generation.incrementAndGet()
        callback = onEvent
        found.clear()
        foundCallbacks = 0
        resolveFailures = 0
        resolvedCallbacks = 0
        identitySuccesses = 0
        identityFailures = 0
        Log.i(TAG, "event=scan_requested generation=$current")
        try {
            lock = wifi.createMulticastLock("ezwincommand-nsd-$current").apply {
                setReferenceCounted(false)
                acquire()
            }
            val discovery = listenerFor(current)
            listener = discovery
            nsd.discoverServices(SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, discovery)
            deadline = scope.launch {
                delay(SCAN_MILLIS)
                finish(current)
            }
        } catch (_: SecurityException) {
            Log.w(TAG, "event=scan_unavailable generation=$current category=permission")
            stopLocked(false)
            onEvent(DiscoveryEvent.Unavailable("发现不可用"))
        } catch (_: RuntimeException) {
            Log.w(TAG, "event=scan_unavailable generation=$current category=runtime")
            stopLocked(false)
            onEvent(DiscoveryEvent.Unavailable("发现不可用"))
        }
    }

    @Synchronized
    private fun listenerFor(current: Long) = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(serviceType: String) {
            Log.i(TAG, "event=scan_started generation=$current type=${safeValue(serviceType)}")
        }

        override fun onServiceFound(service: NsdServiceInfo) {
            synchronized(this@NsdDiscoveryClient) {
                if (generation.get() != current) return
                foundCallbacks++
                val compatible = isCompatibleServiceType(service.serviceType)
                Log.i(TAG, "event=service_found generation=$current name=${safeValue(service.serviceName)} type=${safeValue(service.serviceType)} compatible=$compatible")
                if (!compatible) return
                if (resolveQueue.none { it.serviceName == service.serviceName }) resolveQueue.addLast(service)
                resolveNext(current)
            }
        }

        override fun onServiceLost(service: NsdServiceInfo) {
            Log.i(TAG, "event=service_lost generation=$current name=${safeValue(service.serviceName)}")
        }

        override fun onDiscoveryStopped(serviceType: String) {
            Log.i(TAG, "event=scan_stopped generation=$current")
        }

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.w(TAG, "event=scan_start_failed generation=$current code=$errorCode")
            unavailable(current)
        }

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.w(TAG, "event=scan_stop_failed generation=$current code=$errorCode")
            finish(current)
        }
    }

    @Synchronized
    private fun resolveNext(current: Long) {
        if (generation.get() != current || resolving) return
        val candidate = resolveQueue.pollFirst() ?: return
        resolving = true
        try {
            @Suppress("DEPRECATION")
            nsd.resolveService(candidate, object : NsdManager.ResolveListener {
                override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                    synchronized(this@NsdDiscoveryClient) { resolveFailures++ }
                    Log.w(TAG, "event=resolve_failed generation=$current name=${safeValue(serviceInfo.serviceName)} code=$errorCode")
                    resolved(current, null)
                }

                override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                    synchronized(this@NsdDiscoveryClient) { resolvedCallbacks++ }
                    val address = serviceInfo.host
                    Log.i(TAG, "event=service_resolved generation=$current family=${addressFamily(address?.hostAddress)} port=${serviceInfo.port} scoped=${address?.isLinkLocalAddress == true}")
                    resolved(current, serviceInfo)
                }
            })
        } catch (_: RuntimeException) {
            resolveFailures++
            Log.w(TAG, "event=resolve_exception generation=$current category=runtime")
            resolving = false
            resolveNext(current)
        }
    }

    private fun resolved(current: Long, info: NsdServiceInfo?) {
        synchronized(this) {
            if (generation.get() != current) return
            resolving = false
            if (info != null) verify(current, info)
            resolveNext(current)
        }
    }

    private fun verify(current: Long, info: NsdServiceInfo) {
        val host = normalizedHost(info.host?.hostAddress)
        if (host == null || info.port !in 1..65535) {
            synchronized(this) { identityFailures++ }
            Log.w(TAG, "event=identity_result generation=$current category=invalid_endpoint")
            return
        }
        val baseUrl = "http://${if (host.contains(':')) "[$host]" else host}:${info.port}"
        scope.launch {
            identitySlots.withPermit {
                when (val result = clientFactory(baseUrl).identity()) {
                    is ApiResult.Success -> synchronized(this@NsdDiscoveryClient) {
                        if (generation.get() != current) return@synchronized
                        identitySuccesses++
                        val identity = result.value
                        found[identity.serverId] = DiscoveredServer(identity.serverId, identity.name, baseUrl)
                        Log.i(TAG, "event=identity_result generation=$current category=success servers=${found.size}")
                        callback?.invoke(DiscoveryEvent.Updated(found.values.toList()))
                    }
                    is ApiResult.HttpError -> recordIdentityFailure(current, "http", result.status)
                    is ApiResult.NetworkError -> recordIdentityFailure(current, "network")
                    is ApiResult.ParseError -> recordIdentityFailure(current, "parse")
                }
            }
        }
    }

    @Synchronized
    private fun recordIdentityFailure(current: Long, category: String, status: Int? = null) {
        if (generation.get() != current) return
        identityFailures++
        Log.w(TAG, "event=identity_result generation=$current category=$category${status?.let { " status=$it" }.orEmpty()}")
    }

    private fun unavailable(current: Long) {
        val sink: ((DiscoveryEvent) -> Unit)?
        synchronized(this) {
            if (generation.get() != current) return
            sink = callback
            stopLocked(false)
        }
        sink?.invoke(DiscoveryEvent.Unavailable("发现不可用"))
    }

    private fun finish(current: Long) {
        val sink: ((DiscoveryEvent) -> Unit)?
        val snapshot: List<DiscoveredServer>
        synchronized(this) {
            if (generation.get() != current) return
            sink = callback
            snapshot = found.values.toList()
            Log.i(TAG, "event=scan_finish generation=$current found_callbacks=$foundCallbacks resolved=$resolvedCallbacks resolve_failures=$resolveFailures identity_success=$identitySuccesses identity_failures=$identityFailures servers=${snapshot.size}")
            stopLocked(false)
        }
        sink?.invoke(DiscoveryEvent.Finished(snapshot))
    }

    @Synchronized
    fun stop() {
        generation.incrementAndGet()
        stopLocked(true)
    }

    private fun stopLocked(clearCallback: Boolean) {
        deadline?.cancel()
        deadline = null
        listener?.let { runCatching { nsd.stopServiceDiscovery(it) } }
        listener = null
        resolveQueue.clear()
        resolving = false
        runCatching { if (lock?.isHeld == true) lock?.release() }
        lock = null
        if (clearCallback) callback = null
        Log.i(TAG, "event=resources_released generation=${generation.get()} listener=true multicast=true")
    }

    override fun close() {
        stop()
        scope.coroutineContext[Job]?.cancel()
    }

    internal companion object {
        private const val TAG = "EzNsd"
        const val SERVICE_TYPE = "_ezwincommand._tcp."
        const val SCAN_MILLIS = 8_000L

        internal fun normalizedHost(value: String?): String? = value?.substringBefore('%')?.takeIf { it.isNotBlank() }

        internal fun addressFamily(value: String?): String = when {
            value == null -> "none"
            value.contains(':') -> "ipv6"
            else -> "ipv4"
        }

        private fun safeValue(value: String?): String = value.orEmpty().take(80).replace(Regex("[^A-Za-z0-9._-]"), "_")

        /** Android NSD 回调可能追加 DNS-SD 的 local. 域，比较时仅忽略该规范化差异。 */
        internal fun isCompatibleServiceType(value: String?): Boolean {
            val normalized = value?.trim()?.lowercase()?.trimEnd('.') ?: return false
            return normalized == "_ezwincommand._tcp" || normalized == "_ezwincommand._tcp.local"
        }
    }
}
