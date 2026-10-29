import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FakeHttpResponse:
    def __init__(self, body="", status_code=200, mimetype=None):
        self.body = body
        self.status_code = status_code
        self.mimetype = mimetype


class FakeSnippet:
    def __init__(self, start, duration, text="caption"):
        self.start = start
        self.duration = duration
        self.text = text


class FakeTranscript:
    def __init__(self, snippets, is_generated=None):
        self.snippets = snippets
        self.is_generated = is_generated


class FakeYouTubeTranscriptApi:
    result = None

    def __init__(self, proxy_config=None):
        self.proxy_config = proxy_config

    def fetch(self, video_id):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeWebshareProxyConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


functions_module = types.ModuleType("azure.functions")
functions_module.HttpRequest = object
functions_module.HttpResponse = FakeHttpResponse
azure_module = types.ModuleType("azure")
azure_module.functions = functions_module
proxies_module = types.ModuleType("youtube_transcript_api.proxies")
proxies_module.WebshareProxyConfig = FakeWebshareProxyConfig
youtube_module = types.ModuleType("youtube_transcript_api")
youtube_module.YouTubeTranscriptApi = FakeYouTubeTranscriptApi
sys.modules["azure"] = azure_module
sys.modules["azure.functions"] = functions_module
sys.modules["youtube_transcript_api"] = youtube_module
sys.modules["youtube_transcript_api.proxies"] = proxies_module

function_spec = importlib.util.spec_from_file_location(
    "transcript_function_test",
    Path(__file__).parents[1] / "GetTranscript" / "__init__.py",
    submodule_search_locations=[str(Path(__file__).parents[1] / "GetTranscript")],
)
transcript_function = importlib.util.module_from_spec(function_spec)
sys.modules[function_spec.name] = transcript_function
function_spec.loader.exec_module(transcript_function)


class FakeHttpRequest:
    def __init__(self, video_id):
        self.params = {"videoId": video_id}

    def get_json(self):
        return {}


def event_fields(mock):
    return mock.call_args.kwargs


class TranscriptFunctionTelemetryTests(unittest.TestCase):
    def setUp(self):
        transcript_function.TRANSCRIPT_ANALYTICS_ENABLED = True

    def test_success_emits_one_event_with_caption_and_duration_metadata(self):
        FakeYouTubeTranscriptApi.result = FakeTranscript(
            [FakeSnippet(0, 4), FakeSnippet(290, 20)], is_generated=True
        )
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 200)
        emit.assert_called_once()
        fields = event_fields(emit)
        self.assertEqual(fields["video_id"], "Abcdef12345")
        self.assertEqual(fields["outcome"], "success")
        self.assertEqual(fields["error_type"], "")
        self.assertEqual(fields["caption_type"], "auto")
        self.assertEqual(fields["length_bucket"], "5-15m")
        self.assertGreaterEqual(fields["duration_ms"], 0)

    def test_invalid_id_emits_one_failure_event(self):
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("bad-id"))

        self.assertEqual(response.status_code, 400)
        emit.assert_called_once()
        self.assertEqual(event_fields(emit)["error_type"], "invalid_url")

    def test_no_captions_emits_one_failure_event(self):
        no_captions = type("NoTranscriptFound", (Exception,), {})
        FakeYouTubeTranscriptApi.result = no_captions()
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 422)
        emit.assert_called_once()
        self.assertEqual(event_fields(emit)["error_type"], "transcript_unavailable")

    def test_proxy_block_emits_one_failure_event(self):
        blocked = type("RequestBlocked", (Exception,), {})
        FakeYouTubeTranscriptApi.result = blocked()
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 502)
        emit.assert_called_once()
        self.assertEqual(event_fields(emit)["error_type"], "proxy_blocked")

    def test_rate_limit_emits_one_failure_event(self):
        rate_limited = type("TooManyRequests", (Exception,), {})
        FakeYouTubeTranscriptApi.result = rate_limited()
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 429)
        emit.assert_called_once()
        self.assertEqual(event_fields(emit)["error_type"], "rate_limited")

    def test_invalid_transcript_shape_emits_invalid_response(self):
        FakeYouTubeTranscriptApi.result = object()
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 502)
        emit.assert_called_once()
        self.assertEqual(event_fields(emit)["error_type"], "invalid_response")

    def test_analytics_off_preserves_api1_behavior_and_emits_nothing(self):
        blocked = type("RequestBlocked", (Exception,), {})
        FakeYouTubeTranscriptApi.result = blocked()
        transcript_function.TRANSCRIPT_ANALYTICS_ENABLED = False
        with patch.object(transcript_function, "emit_transcript_request_completed") as emit:
            response = transcript_function.main(FakeHttpRequest("Abcdef12345"))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(json.loads(response.body)["error"], "upstream_error")
        emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
