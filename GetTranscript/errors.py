TRANSCRIPT_UNAVAILABLE_EXCEPTIONS = {
    "NoTranscriptFound",
    "TranscriptsDisabled",
    "TranslationLanguageNotAvailable",
}
VIDEO_UNAVAILABLE_EXCEPTIONS = {
    "AgeRestricted",
    "VideoUnavailable",
    "VideoUnplayable",
}
PROXY_BLOCKED_EXCEPTIONS = {"RequestBlocked", "IpBlocked", "ProxyError"}
RATE_LIMITED_EXCEPTIONS = {"TooManyRequests", "RateLimitExceeded"}
TIMEOUT_EXCEPTIONS = {"Timeout", "ConnectTimeout", "ReadTimeout", "TimeoutError"}
NETWORK_EXCEPTIONS = {"ConnectionError", "ConnectionResetError", "NewConnectionError"}


def _exception_chain(error):
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def classify_transcript_error(error, analytics_enabled=False):
    chain = list(_exception_chain(error))
    names = {type(item).__name__ for item in chain}

    if names & TRANSCRIPT_UNAVAILABLE_EXCEPTIONS:
        return "transcript_unavailable"
    if names & VIDEO_UNAVAILABLE_EXCEPTIONS:
        return "video_unavailable"

    if analytics_enabled:
        if names & PROXY_BLOCKED_EXCEPTIONS:
            return "proxy_blocked"
        if names & RATE_LIMITED_EXCEPTIONS:
            return "rate_limited"
        if names & TIMEOUT_EXCEPTIONS:
            return "timeout"
        if names & NETWORK_EXCEPTIONS:
            return "network_error"
        if "InvalidVideoId" in names:
            return "invalid_url"
        if names & {"YouTubeDataUnparsable", "InvalidTranscriptResponse"}:
            return "invalid_response"

        for item in chain:
            response = getattr(item, "response", None)
            if getattr(response, "status_code", None) == 429:
                return "rate_limited"
            reason = str(getattr(item, "reason", "")).lower()
            if "429" in reason or "too many requests" in reason:
                return "rate_limited"
            if "proxyerror" in reason or "proxy error" in reason:
                return "proxy_blocked"

        if "YouTubeRequestFailed" in names:
            return "upstream_error"
        return "unknown"

    return "upstream_error"
