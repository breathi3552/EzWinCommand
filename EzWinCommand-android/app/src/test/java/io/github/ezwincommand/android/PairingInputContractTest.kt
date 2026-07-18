package io.github.ezwincommand.android

import org.junit.Assert.assertEquals
import org.junit.Test

class PairingInputContractTest {
    @Test
    fun `mixed input keeps first four ASCII digits`() {
        assertEquals("1234", sanitizePairingCode("1a２2-345"))
    }

    @Test
    fun `device name truncation counts Unicode code points`() {
        val value = "😀".repeat(129)
        val truncated = truncateDeviceName("  $value  ")
        assertEquals(128, truncated.codePointCount(0, truncated.length))
        assertEquals("😀".repeat(128), truncated)
    }

    @Test
    fun `readable name follows market build deduplication and fallback order`() {
        assertEquals("Pixel Phone", resolveReadableDeviceName(" Pixel Phone ", "Google", "Pixel", "Android"))
        assertEquals("Google Pixel", resolveReadableDeviceName(null, "Google", "Pixel", "Android"))
        assertEquals("Pixel", resolveReadableDeviceName(null, "Pixel", "pixel", "Android"))
        assertEquals("Android", resolveReadableDeviceName(" ", " ", "", "Android"))
    }
}
