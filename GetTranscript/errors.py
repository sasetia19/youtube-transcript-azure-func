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


def classify_transcript_error(error):
    error_name = type(error).__name__
    if error_name in TRANSCRIPT_UNAVAILABLE_EXCEPTIONS:
        return "transcript_unavailable"
    if error_name in VIDEO_UNAVAILABLE_EXCEPTIONS:
        return "video_unavailable"
    return "upstream_error"
