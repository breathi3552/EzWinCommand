package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaPlayback
import io.github.ezwincommand.android.model.MediaState
import org.junit.Assert.assertEquals
import org.junit.Test

class MediaBusyMergeTest {
    private val displayed = MediaState.LOADING.copy(volume = 73, title = "旧歌")
    private val authoritative = MediaState.LOADING.copy(
        revision = 9,
        available = true,
        title = "新歌",
        artist = "新艺术家",
        playback = MediaPlayback.PLAYING,
        volume = 20,
        renderDevices = listOf(AudioEndpoint("out", "新扬声器")),
        captureDevices = listOf(AudioEndpoint("in", "新麦克风")),
        selectedRenderId = "out",
        selectedCaptureId = "in",
        error = "局部错误",
    )

    @Test
    fun `busy SSE updates all media fields except displayed volume`() {
        val merged = mergeAuthoritativeMedia(displayed, authoritative, volumeBusy = true)
        assertEquals(73, merged.volume)
        assertEquals("新歌", merged.title)
        assertEquals(MediaPlayback.PLAYING, merged.playback)
        assertEquals("out", merged.selectedRenderId)
        assertEquals("局部错误", merged.error)
    }

    @Test
    fun `authoritative success clears historical initialization timeout`() {
        val failed = displayed.copy(error = "媒体服务初始化超时")
        val recovered = authoritative.copy(error = null)

        val merged = mergeAuthoritativeMedia(failed, recovered, volumeBusy = false)

        assertEquals(null, merged.error)
    }

    @Test
    fun `authoritative current failure remains visible after merge`() {
        val failed = authoritative.copy(error = "媒体服务连接失败")

        val merged = mergeAuthoritativeMedia(displayed.copy(error = "媒体服务初始化超时"), failed, volumeBusy = false)

        assertEquals("媒体服务连接失败", merged.error)
    }

    @Test
    fun `idle converges to authoritative volume`() {
        assertEquals(20, mergeAuthoritativeMedia(displayed, authoritative, volumeBusy = false).volume)
    }
}
