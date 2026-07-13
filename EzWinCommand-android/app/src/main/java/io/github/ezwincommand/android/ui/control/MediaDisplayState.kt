package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState

internal fun mergeAuthoritativeMedia(
    displayed: MediaState,
    authoritative: MediaState,
    volumeBusy: Boolean,
): MediaState = if (volumeBusy) authoritative.copy(volume = displayed.volume) else authoritative
