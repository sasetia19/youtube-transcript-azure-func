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


if __name__ == "__main__":
    unittest.main()
