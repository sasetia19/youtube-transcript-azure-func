import importlib.util
import unittest
from pathlib import Path

error_spec = importlib.util.spec_from_file_location(
    "transcript_errors", Path(__file__).parents[1] / "GetTranscript" / "errors.py"
)
errors = importlib.util.module_from_spec(error_spec)
error_spec.loader.exec_module(errors)


class TranscriptErrorClassificationTests(unittest.TestCase):
    def test_no_caption_errors_are_grouped(self):
        for error_name in (
            "NoTranscriptFound",
            "TranscriptsDisabled",
            "TranslationLanguageNotAvailable",
        ):
            error_type = type(error_name, (Exception,), {})
            with self.subTest(error_name=error_name):
                self.assertEqual(
                    errors.classify_transcript_error(error_type("private detail")),
                    "transcript_unavailable",
                )

    def test_unavailable_videos_are_grouped(self):
        for error_name in ("AgeRestricted", "VideoUnavailable", "VideoUnplayable"):
            error_type = type(error_name, (Exception,), {})
            with self.subTest(error_name=error_name):
                self.assertEqual(
                    errors.classify_transcript_error(error_type("private detail")),
                    "video_unavailable",
                )

    def test_unknown_errors_do_not_leak_exception_message(self):
        error = RuntimeError("secret video id and upstream response")
        self.assertEqual(errors.classify_transcript_error(error), "upstream_error")

    def test_api2_maps_proxy_and_rate_limit_exceptions(self):
        for error_name in ("RequestBlocked", "IpBlocked", "ProxyError"):
            error_type = type(error_name, (Exception,), {})
            with self.subTest(error_name=error_name):
                self.assertEqual(
                    errors.classify_transcript_error(
                        error_type("proxy details"), analytics_enabled=True
                    ),
                    "proxy_blocked",
                )

        too_many_requests = type("TooManyRequests", (Exception,), {})
        self.assertEqual(
            errors.classify_transcript_error(
                too_many_requests(), analytics_enabled=True
            ),
            "rate_limited",
        )

    def test_api2_maps_wrapped_http_429_and_invalid_responses(self):
        request_failed = type("YouTubeRequestFailed", (Exception,), {})
        error = request_failed()
        error.reason = "429 Client Error: Too Many Requests"
        self.assertEqual(
            errors.classify_transcript_error(error, analytics_enabled=True),
            "rate_limited",
        )

        invalid_response = type("InvalidTranscriptResponse", (Exception,), {})
        self.assertEqual(
            errors.classify_transcript_error(
                invalid_response(), analytics_enabled=True
            ),
            "invalid_response",
        )

    def test_api2_maps_timeout_network_and_invalid_video(self):
        for error_name, expected in (
            ("ReadTimeout", "timeout"),
            ("ConnectionError", "network_error"),
            ("InvalidVideoId", "invalid_url"),
        ):
            error_type = type(error_name, (Exception,), {})
            with self.subTest(error_name=error_name):
                self.assertEqual(
                    errors.classify_transcript_error(
                        error_type(), analytics_enabled=True
                    ),
                    expected,
                )

    def test_legacy_classification_remains_unchanged_when_api2_flag_is_off(self):
        blocked = type("RequestBlocked", (Exception,), {})
        self.assertEqual(errors.classify_transcript_error(blocked()), "upstream_error")


if __name__ == "__main__":
    unittest.main()
