import importlib.util
import json
import sys
import types
import unittest
from urllib.parse import urlsplit
from pathlib import Path
from urllib.request import Request
from unittest.mock import patch


class FakeHttpResponse:
    def __init__(self, body="", status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}


class FakeUpstreamResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b'{"ok": true}'


azure_module = types.ModuleType("azure")
functions_module = types.ModuleType("azure.functions")
functions_module.HttpRequest = object
functions_module.HttpResponse = FakeHttpResponse
azure_module.functions = functions_module
sys.modules.setdefault("azure", azure_module)
sys.modules.setdefault("azure.functions", functions_module)

function_dir = Path(__file__).parents[1] / "Feedback"
function_spec = importlib.util.spec_from_file_location(
    "feedback_test_endpoint",
    function_dir / "__init__.py",
    submodule_search_locations=[str(function_dir)],
)
endpoint = importlib.util.module_from_spec(function_spec)
sys.modules[function_spec.name] = endpoint
function_spec.loader.exec_module(endpoint)


class FakeHttpRequest:
    method = "POST"

    def __init__(self, payload, token="test-session-token-123456", origin="https://transcriptsx.com"):
        self.headers = {
            "origin": origin,
            "x-feedback-session": token,
        }
        self.body = json.dumps(payload).encode("utf-8")

    def get_body(self):
        return self.body


def tab_payload(**updates):
    payload = {
        "source": "tab",
        "category": "something_broke",
        "message": "The transcript did not load",
        "email": "",
        "page_path": "/",
        "user_agent": "test-agent",
        "viewport_width": 360,
        "website": "",
        "include_video_url": False,
    }
    payload.update(updates)
    return payload


class FeedbackEndpointTests(unittest.TestCase):
    def setUp(self):
        endpoint.RATE_LIMITER = endpoint.InMemoryRateLimiter(limit=5, window_seconds=3600)

    def test_honeypot_submission_is_silently_discarded(self):
        with patch.object(endpoint, "_submit_to_sheet") as submit:
            response = endpoint.main(FakeHttpRequest(tab_payload(website="filled by bot")))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, '{"ok": true}')
        submit.assert_not_called()

    def test_honeypot_and_real_submission_have_identical_success_response(self):
        with patch.object(endpoint, "_submit_to_sheet", return_value=True):
            real_response = endpoint.main(FakeHttpRequest(tab_payload()))
            honey_response = endpoint.main(
                FakeHttpRequest(tab_payload(website="bot"), token="other-session-token-12345")
            )
        self.assertEqual(
            (honey_response.status_code, honey_response.body),
            (real_response.status_code, real_response.body),
        )

    def test_production_default_cors_is_site_origin_only(self):
        with patch.dict(endpoint.os.environ, {}, clear=True):
            self.assertEqual(endpoint._allowed_origins(), {"https://transcriptsx.com"})

    def test_local_origins_require_explicit_local_configuration(self):
        local_origins = "http://localhost:8080,http://127.0.0.1:8080"
        with patch.dict(endpoint.os.environ, {"FEEDBACK_ALLOWED_ORIGINS": local_origins}):
            self.assertEqual(
                endpoint._allowed_origins(),
                {"http://localhost:8080", "http://127.0.0.1:8080"},
            )

    def test_apps_script_secret_is_post_body_not_query(self):
        upstream = FakeUpstreamResponse()
        with patch.dict(endpoint.os.environ, {
            "FEEDBACK_APPS_SCRIPT_URL": "https://script.google.com/macros/s/example/exec",
            "FEEDBACK_APPS_SCRIPT_SECRET": "not-a-real-secret",
        }), patch("urllib.request.build_opener") as build_opener:
            build_opener.return_value.open.return_value = upstream
            self.assertTrue(endpoint._submit_to_sheet({"message": "hello"}))

        request = build_opener.return_value.open.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(urlsplit(request.full_url).query, "")
        self.assertEqual(json.loads(request.data)["secret"], "not-a-real-secret")

    def test_rate_limiter_blocks_sixth_submission(self):
        endpoint.RATE_LIMITER = endpoint.InMemoryRateLimiter(limit=5, window_seconds=3600)
        with patch.object(endpoint, "_submit_to_sheet", return_value=True) as submit:
            responses = [
                endpoint.main(FakeHttpRequest(tab_payload()))
                for _ in range(6)
            ]
        self.assertEqual([response.status_code for response in responses], [200] * 5 + [429])
        self.assertEqual(submit.call_count, 5)

    def test_rejects_disallowed_origin(self):
        with patch.object(endpoint, "_submit_to_sheet") as submit:
            response = endpoint.main(
                FakeHttpRequest(tab_payload(), origin="https://evil.example")
            )
        self.assertEqual(response.status_code, 403)
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
