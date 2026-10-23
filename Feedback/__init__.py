import json
import os
import re
import urllib.request
import uuid
from datetime import datetime, timezone

import azure.functions as func

from .core import InMemoryRateLimiter, sanitize_sheet_value, validate_payload

PRODUCTION_ORIGINS = {"https://transcriptsx.com"}
SESSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9-]{16,128}$")
MAX_BODY_BYTES = 16384
RATE_LIMITER = InMemoryRateLimiter(limit=5, window_seconds=3600)


class AppsScriptRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if code in {301, 302, 303} and request.get_method() == "POST":
            return urllib.request.Request(new_url, method="GET")
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


def _allowed_origins():
    configured = os.getenv("FEEDBACK_ALLOWED_ORIGINS")
    if configured is None:
        return PRODUCTION_ORIGINS
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


def _response(status_code, body=None, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin and origin in _allowed_origins():
        headers.update({
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Feedback-Session",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        })
    payload = "" if body is None else json.dumps(body)
    return func.HttpResponse(body=payload, status_code=status_code, headers=headers)


def _submit_to_sheet(record):
    script_url = os.getenv("FEEDBACK_APPS_SCRIPT_URL")
    shared_secret = os.getenv("FEEDBACK_APPS_SCRIPT_SECRET")
    if not script_url or not shared_secret:
        return False

    payload = {key: sanitize_sheet_value(value) for key, value in record.items()}
    payload["secret"] = shared_secret
    request = urllib.request.Request(
        script_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(AppsScriptRedirectHandler)
        with opener.open(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and result.get("ok") is True
    except Exception:
        return False


def main(req: func.HttpRequest) -> func.HttpResponse:
    origin = req.headers.get("origin")
    if origin not in _allowed_origins():
        return _response(403)

    if req.method.upper() == "OPTIONS":
        return _response(204, origin=origin)
    if req.method.upper() != "POST":
        return _response(405, {"error": "Method not allowed"}, origin)

    body = req.get_body()
    if len(body) > MAX_BODY_BYTES:
        return _response(413, {"error": "Feedback is too large"}, origin)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _response(400, {"error": "Invalid request"}, origin)

    session_token = req.headers.get("x-feedback-session", "")
    if not SESSION_TOKEN_RE.fullmatch(session_token):
        return _response(400, {"error": "Invalid request"}, origin)

    try:
        record = validate_payload(data)
    except ValueError:
        return _response(400, {"error": "Invalid feedback"}, origin)

    if record["website"].strip():
        return _response(200, {"ok": True}, origin)
    if not RATE_LIMITER.allow(session_token):
        return _response(429, {"error": "Please try again later"}, origin)

    record.pop("website", None)
    record.update({
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })

    if not _submit_to_sheet(record):
        return _response(502, {"error": "Could not submit feedback"}, origin)
    return _response(200, {"ok": True}, origin)
