package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.R
import io.github.ezwincommand.android.model.MediaPlayback
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaCardContractTest {
    @Test
    fun `three media icon buttons expose exact actions descriptions and touch targets`() {
        val specs = mediaButtonSpecs(true, MediaPlayback.PLAYING)
        assertEquals(listOf("prev", "play_pause", "next"), specs.map { it.subAction })
        assertEquals(listOf(R.string.media_previous, R.string.media_pause, R.string.media_next), specs.map { it.contentDescription })
        assertEquals(listOf(48, 56, 48), specs.map { it.touchTargetDp })
        assertTrue(specs.all { it.enabled })
    }

    @Test
    fun `unavailable media retains controls disabled with unavailable descriptions`() {
        val specs = mediaButtonSpecs(false, MediaPlayback.NONE)
        assertTrue(specs.all { !it.enabled })
        assertEquals(R.string.media_previous_disabled, specs.first().contentDescription)
        assertEquals(R.string.media_play_pause_disabled, specs[1].contentDescription)
        assertEquals(R.string.media_next_disabled, specs.last().contentDescription)
        assertFalse(specs.any { it.touchTargetDp < 48 })
    }
}
