import importlib.util
import logging
import unittest
from pathlib import Path
from unittest.mock import Mock

telemetry_spec = importlib.util.spec_from_file_location(
    "transcript_telemetry", Path(__file__).parents[1] / "GetTranscript" / "telemetry.py"
)
telemetry = importlib.util.module_from_spec(telemetry_spec)
telemetry_spec.loader.exec_module(telemetry)


class TranscriptTelemetryTests(unittest.TestCase):
    def test_duration_buckets_and_unknown_values(self):
        cases = (
            (0, "<5m"),
            (299.9, "<5m"),
            (300, "5-15m"),
            (899.9, "5-15m"),
            (900, "15-60m"),
            (3599.9, "15-60m"),
            (3600, "60m+"),
            (None, "unknown"),
            (-1, "unknown"),
        )
        for duration, expected in cases:
            with self.subTest(duration=duration):
                self.assertEqual(telemetry.length_bucket(duration), expected)

    def test_event_has_only_the_required_dimensions(self):
        logger = Mock()
        telemetry.TRANSCRIPT_ANALYTICS_ENABLED = True
        telemetry.emit_transcript_request_completed(
            video_id="Abcdef12345",
            outcome="success",
            error_type="",
            duration_ms=1200.5,
            caption_type="auto",
            length_bucket="5-15m",
            event_logger=logger,
        )
        logger.info.assert_called_once()
        message, = logger.info.call_args.args
        self.assertEqual(message, "transcript_request_completed")
        dimensions = logger.info.call_args.kwargs["extra"]
        self.assertEqual(
            set(dimensions),
            {
                "microsoft.custom_event.name",
                "video_id",
                "outcome",
                "error_type",
                "duration_ms",
                "caption_type",
                "length_bucket",
            },
        )
        self.assertEqual(dimensions["video_id"], "Abcdef12345")
        self.assertEqual(dimensions["microsoft.custom_event.name"], telemetry.EVENT_NAME)

    def test_telemetry_failures_do_not_escape_or_block_request_code(self):
        logger = Mock()
        logger.info.side_effect = RuntimeError("export failure")
        telemetry.TRANSCRIPT_ANALYTICS_ENABLED = True
        telemetry.emit_transcript_request_completed(
            video_id="Abcdef12345",
            outcome="failure",
            error_type="proxy_blocked",
            duration_ms=5,
            caption_type="unknown",
            length_bucket="unknown",
            event_logger=logger,
        )

    def test_event_is_not_emitted_when_disabled(self):
        logger = Mock()
        telemetry.TRANSCRIPT_ANALYTICS_ENABLED = False
        telemetry.emit_transcript_request_completed(
            video_id="Abcdef12345",
            outcome="success",
            error_type="",
            duration_ms=1,
            caption_type="manual",
            length_bucket="<5m",
            event_logger=logger,
        )
        logger.info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
