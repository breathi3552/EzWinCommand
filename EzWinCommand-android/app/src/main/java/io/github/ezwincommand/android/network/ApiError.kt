package io.github.ezwincommand.android.network

sealed interface ApiResult<out T> {
    data class Success<T>(val value: T) : ApiResult<T>

    data class HttpError(
        val status: Int,
        val message: String,
    ) : ApiResult<Nothing>

    data class NetworkError(
        val message: String,
        val cause: Throwable? = null,
    ) : ApiResult<Nothing>

    data class ParseError(
        val message: String,
        val cause: Throwable? = null,
    ) : ApiResult<Nothing>
}
