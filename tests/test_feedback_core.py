import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

core_spec = spec_from_file_location(
    "feedback_core", Path(__file__).parents[1] / "Feedback" / "core.py"
)
core = module_from_spec(core_spec)
core_spec.loader.exec_module(core)
InMemoryRateLimiter = core.InMemoryRateLimiter
sanitize_sheet_value = core.sanitize_sheet_value
validate_payload = core.validate_payload


class FeedbackCoreTests(unittest.TestCase):
    def base_payload(self, **updates):
        payload = {
            "source": "tab",
            "category": "something_broke",
            "message": "It did not work",
            "page_path": "/",
            "user_agent": "test-agent",
            "viewport_width": 360,
            "website": "",
        }
        payload.update(updates)
        return payload

    def test_accepts_valid_tab_payload_without_video_url(self):
        record = validate_payload(self.base_payload(video_url="https://youtu.be/private"))
        self.assertIsNone(record["video_url"])

    def test_preserves_opt_in_link_text_for_failed_url_feedback(self):
        record = validate_payload(
            self.base_payload(include_video_url=True, video_url="not a valid link")
        )
        self.assertEqual(record["video_url"], "not a valid link")

    def test_failure_category_can_be_changed_from_default(self):
        record = validate_payload(
            self.base_payload(source="failure", category="idea", error_type="unknown")
        )
        self.assertEqual(record["category"], "idea")

    def test_rejects_invalid_category_email_and_message_length(self):
        for updates in (
            {"category": "rating"},
            {"email": "not-an-email"},
            {"message": "x" * 1001},
        ):
            with self.subTest(updates=updates):
                with self.assertRaises(ValueError):
                    validate_payload(self.base_payload(**updates))

    def test_requires_survey_helpfulness_and_valid_use_case(self):
        payload = self.base_payload(
            source="survey", category=None, message="", helpful=True,
            use_case="other", use_case_other="", email="",
        )
        self.assertEqual(validate_payload(payload)["use_case"], "other")
        payload["helpful"] = None
        with self.assertRaises(ValueError):
            validate_payload(payload)
        payload["helpful"] = True
        payload["use_case"] = "invalid"
        with self.assertRaises(ValueError):
            validate_payload(payload)

    def test_honeypot_is_preserved_for_silent_discard(self):
        self.assertEqual(validate_payload(self.base_payload(website="bot"))["website"], "bot")

    def test_formula_prefixes_are_neutralized(self):
        for value in ("=1+1", "+SUM(A1)", "-2+3", "@cmd", "\ttext", "\rtext", "  =1+1"):
            with self.subTest(value=value):
                self.assertTrue(sanitize_sheet_value(value).startswith("'"))
        self.assertEqual(sanitize_sheet_value("safe"), "safe")

    def test_rate_limit_caps_at_five_and_expires(self):
        limiter = InMemoryRateLimiter(limit=5, window_seconds=3600)
        for attempt in range(5):
            self.assertTrue(limiter.allow("session-token-123456", now=attempt))
        self.assertFalse(limiter.allow("session-token-123456", now=5))
        self.assertTrue(limiter.allow("session-token-123456", now=3601))


if __name__ == "__main__":
    unittest.main()
