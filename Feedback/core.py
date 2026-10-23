import re
import threading
import time
from collections import deque

SOURCES = {"tab", "survey", "failure"}
CATEGORIES = {"something_broke", "something_missing", "idea", "other"}
USE_CASES = {
    "study_notes",
    "content_repurposing",
    "research",
    "translation",
    "accessibility",
    "other",
}
ERROR_TYPES = {
    "invalid_url",
    "fetch_timeout",
    "network_error",
    "no_captions",
    "http_error",
    "parse_error",
    "unknown",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _text(data, name, maximum, required=False):
    value = data.get(name, "")
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Invalid " + name)
    if required and not value.strip():
        raise ValueError("Missing " + name)
    return value


def _enum(data, name, choices, required=False):
    value = data.get(name)
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str) or value not in choices:
        raise ValueError("Invalid " + name)
    return value


def validate_payload(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid payload")

    source = _enum(data, "source", SOURCES, required=True)
    category = _enum(data, "category", CATEGORIES, required=source != "survey")

    message = _text(data, "message", 1000, required=source != "survey")
    email = _text(data, "email", 254).strip()
    if email and not EMAIL_RE.fullmatch(email):
        raise ValueError("Invalid email")

    use_case = _enum(data, "use_case", USE_CASES, required=False)
    use_case_other = _text(data, "use_case_other", 200)
    helpful = data.get("helpful")
    if source == "survey":
        if not isinstance(helpful, bool):
            raise ValueError("Invalid helpful value")
        if use_case != "other" and use_case_other:
            raise ValueError("Unexpected use case details")
        if category is not None or email:
            raise ValueError("Unexpected survey fields")
    elif use_case is not None or use_case_other or helpful is not None:
        raise ValueError("Unexpected survey fields")

    error_type = _enum(data, "error_type", ERROR_TYPES, required=source == "failure")
    if source != "failure" and error_type is not None:
        raise ValueError("Unexpected error type")

    include_video_url = data.get("include_video_url", False)
    if not isinstance(include_video_url, bool):
        raise ValueError("Invalid video link selection")
    video_url = None
    if include_video_url:
        video_url = _text(data, "video_url", 2048, required=True).strip()

    page_path = _text(data, "page_path", 500, required=True)
    if not page_path.startswith("/") or "?" in page_path or "#" in page_path:
        raise ValueError("Invalid page path")
    user_agent = _text(data, "user_agent", 500)
    viewport_width = data.get("viewport_width")
    if isinstance(viewport_width, bool) or not isinstance(viewport_width, int):
        raise ValueError("Invalid viewport width")
    if viewport_width < 0 or viewport_width > 10000:
        raise ValueError("Invalid viewport width")

    return {
        "source": source,
        "category": category,
        "use_case": use_case,
        "use_case_other": use_case_other.strip() or None,
        "helpful": helpful if source == "survey" else None,
        "message": message,
        "email": email or None,
        "page_path": page_path,
        "user_agent": user_agent,
        "viewport_width": viewport_width,
        "error_type": error_type,
        "video_url": video_url,
        "website": _text(data, "website", 200),
    }


def sanitize_sheet_value(value):
    if not isinstance(value, str):
        return value
    first_non_space = value.lstrip(" \t\r\n")[:1]
    if value[:1] in FORMULA_PREFIXES or first_non_space in FORMULA_PREFIXES:
        return "'" + value
    return value


class InMemoryRateLimiter:
    def __init__(self, limit=5, window_seconds=3600, max_tokens=10000):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_tokens = max_tokens
        self._attempts = {}
        self._lock = threading.Lock()

    def allow(self, token, now=None):
        current_time = time.time() if now is None else now
        cutoff = current_time - self.window_seconds
        with self._lock:
            for existing_token, attempts in list(self._attempts.items()):
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if not attempts:
                    del self._attempts[existing_token]

            attempts = self._attempts.get(token)
            if attempts is None:
                if len(self._attempts) >= self.max_tokens:
                    return False
                attempts = deque()
                self._attempts[token] = attempts
            if len(attempts) >= self.limit:
                return False
            attempts.append(current_time)
            return True
