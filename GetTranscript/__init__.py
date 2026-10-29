import azure.functions as func
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import logging
import os
import json
import re
import time

from .errors import classify_transcript_error
from .telemetry import (
    TRANSCRIPT_ANALYTICS_ENABLED,
    emit_transcript_request_completed,
    length_bucket,
)

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
UNAVAILABLE_ERRORS = {"transcript_unavailable", "video_unavailable"}


def _response(error, status_code):
    return func.HttpResponse(
        json.dumps({"error": error}),
        mimetype="application/json",
        status_code=status_code,
    )


def _main_with_analytics(req: func.HttpRequest) -> func.HttpResponse:
    started_at = time.perf_counter()
    video_id = ""
    event_fields = {
        "outcome": "failure",
        "error_type": "unknown",
        "caption_type": "unknown",
        "length_bucket": "unknown",
    }
    try:
        video_id = req.params.get("videoId") or ""
        if not video_id:
            try:
                req_body = req.get_json()
            except ValueError:
                req_body = {}
            if isinstance(req_body, dict):
                video_id = req_body.get("videoId") or ""

        event_fields["video_id"] = video_id if isinstance(video_id, str) else ""
        if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
            event_fields["error_type"] = "invalid_url"
            return _response("invalid_url", 400)

        ytt_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=os.getenv("PROXY_USER"),
                proxy_password=os.getenv("PROXY_PASS"),
            )
        )
        transcript_obj = ytt_api.fetch(video_id)
        try:
            snippets = transcript_obj.snippets
            transcript = [
                {"start": snippet.start, "duration": snippet.duration, "text": snippet.text}
                for snippet in snippets
            ]
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidTranscriptResponse() from error

        if not transcript:
            event_fields["error_type"] = "transcript_unavailable"
            return _response("transcript_unavailable", 422)

        generated = getattr(transcript_obj, "is_generated", None)
        event_fields["caption_type"] = (
            "auto" if generated is True else "manual" if generated is False else "unknown"
        )
        try:
            duration_seconds = max(
                float(segment["start"]) + float(segment["duration"])
                for segment in transcript
            )
            event_fields["length_bucket"] = length_bucket(duration_seconds)
        except (KeyError, TypeError, ValueError):
            event_fields["length_bucket"] = "unknown"

        event_fields["outcome"] = "success"
        event_fields["error_type"] = ""
        return func.HttpResponse(
            json.dumps({"videoId": video_id, "transcript": transcript}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as error:
        error_code = classify_transcript_error(
            error, analytics_enabled=TRANSCRIPT_ANALYTICS_ENABLED
        )
        event_fields["error_type"] = error_code
        status_code = {
            "invalid_url": 400,
            "transcript_unavailable": 422,
            "video_unavailable": 422,
            "rate_limited": 429,
            "timeout": 504,
        }.get(error_code, 502)
        return _response(error_code, status_code)
    finally:
        if TRANSCRIPT_ANALYTICS_ENABLED:
            try:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                emit_transcript_request_completed(
                    video_id=event_fields.get("video_id", ""),
                    outcome=event_fields["outcome"],
                    error_type=event_fields["error_type"],
                    duration_ms=duration_ms,
                    caption_type=event_fields["caption_type"],
                    length_bucket=event_fields["length_bucket"],
                )
            except Exception:
                pass


def _main_legacy(req: func.HttpRequest) -> func.HttpResponse:
    video_id = req.params.get("videoId")
    if not video_id:
        try:
            req_body = req.get_json()
        except ValueError:
            req_body = {}
        video_id = req_body.get("videoId")

    if not video_id:
        return func.HttpResponse(
            json.dumps({"error": "invalid_request"}),
            mimetype="application/json",
            status_code=400,
        )

    try:
        ytt_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=os.getenv("PROXY_USER"),
                proxy_password=os.getenv("PROXY_PASS"),
            )
        )
        transcript_obj = ytt_api.fetch(video_id)
        transcript = [
            {"start": snippet.start, "duration": snippet.duration, "text": snippet.text}
            for snippet in transcript_obj.snippets
        ]
        if not transcript:
            logging.warning("transcript_fetch_failed category=transcript_unavailable")
            return _response("transcript_unavailable", 422)
        return func.HttpResponse(
            json.dumps({"videoId": video_id, "transcript": transcript}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as error:
        error_code = classify_transcript_error(error)
        logging.warning("transcript_fetch_failed category=%s", error_code)
        status_code = 422 if error_code in UNAVAILABLE_ERRORS else 502
        return _response(error_code, status_code)


def main(req: func.HttpRequest) -> func.HttpResponse:
    if TRANSCRIPT_ANALYTICS_ENABLED:
        return _main_with_analytics(req)
    return _main_legacy(req)


class InvalidTranscriptResponse(Exception):
    pass
