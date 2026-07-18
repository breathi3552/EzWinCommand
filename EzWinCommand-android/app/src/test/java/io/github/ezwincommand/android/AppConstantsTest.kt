package io.github.ezwincommand.android

import kotlin.test.Test
import kotlin.test.assertEquals

class AppConstantsTest {

    @Test
    fun exposesExpectedDefaults() {
        assertEquals(8080, AppConstants.DEFAULT_PORT)
        assertEquals("http", AppConstants.DEFAULT_SCHEME)
    }
}

class NsdEndpointContractTest {
    @org.junit.Test
    fun `IPv6 scope is removed before URL formatting`() {
        kotlin.test.assertEquals("fe80::1234", io.github.ezwincommand.android.network.NsdDiscoveryClient.normalizedHost("fe80::1234%wlan0"))
        kotlin.test.assertEquals("ipv6", io.github.ezwincommand.android.network.NsdDiscoveryClient.addressFamily("fe80::1234%wlan0"))
        kotlin.test.assertEquals("ipv4", io.github.ezwincommand.android.network.NsdDiscoveryClient.addressFamily("192.168.31.87"))
    }
}
