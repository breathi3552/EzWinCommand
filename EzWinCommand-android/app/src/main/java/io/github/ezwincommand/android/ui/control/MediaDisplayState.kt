package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState

internal fun mergeAuthoritativeMedia(
    displayed: MediaState,
    authoritative: MediaState,
    volumeBusy: Boolean,
): MediaState {
    // authoritative.error 是当前服务状态；成功状态的 null 必须清除历史 transient error。
    // 不从 displayed 继承 error，避免初始化超时在服务恢复后驻留。
    return authoritative.copy(
        volume = if (volumeBusy) displayed.volume else authoritative.volume,
        error = authoritative.error,
    )
}
