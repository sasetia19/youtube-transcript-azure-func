import logging
import os

EVENT_NAME = "transcript_request_completed"
LOGGER_NAME = "transcriptx.request.analytics"
TRANSCRIPT_ANALYTICS_ENABLED = (
    os.getenv("TRANSCRIPT_ANALYTICS_ENABLED", "").lower() == "true"
)


def _create_logger():
    if not TRANSCRIPT_ANALYTICS_ENABLED:
        logging.getLogger().info("transcript_analytics_disabled")
        return None
    try:
        from microsoft.opentelemetry import use_microsoft_opentelemetry

        use_microsoft_opentelemetry(
            enable_azure_monitor=True,
            logger_name=LOGGER_NAME,
        )
        event_logger = logging.getLogger(LOGGER_NAME)
        event_logger.setLevel(logging.INFO)
        logging.getLogger().info("transcript_analytics_initialized")
        return event_logger
    except Exception as error:
        logging.getLogger().warning(
            "transcript_analytics_initialization_failed exception_type=%s",
            type(error).__name__,
        )
        return None


_EVENT_LOGGER = _create_logger()


def emit_transcript_request_completed(
    *,
    video_id,
    outcome,
    error_type,
    duration_ms,
    caption_type,
    length_bucket,
    event_logger=None,
):
    if not TRANSCRIPT_ANALYTICS_ENABLED:
        return

    try:
        active_logger = event_logger or _EVENT_LOGGER
        if active_logger is None:
            return
        active_logger.info(
            EVENT_NAME,
            extra={
                "microsoft.custom_event.name": EVENT_NAME,
                "video_id": video_id or "",
                "outcome": outcome,
                "error_type": error_type or "",
                "duration_ms": duration_ms,
                "caption_type": caption_type,
                "length_bucket": length_bucket,
            },
        )
    except Exception as error:
        logging.getLogger().warning(
            "transcript_analytics_emit_failed exception_type=%s",
            type(error).__name__,
        )
        return


def length_bucket(duration_seconds):
    if not isinstance(duration_seconds, (int, float)) or duration_seconds < 0:
        return "unknown"
    if duration_seconds < 5 * 60:
        return "<5m"
    if duration_seconds < 15 * 60:
        return "5-15m"
    if duration_seconds < 60 * 60:
        return "15-60m"
    return "60m+"
