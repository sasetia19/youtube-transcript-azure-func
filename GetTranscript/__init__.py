import azure.functions as func
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import logging
import os
import json

from .errors import classify_transcript_error


def main(req: func.HttpRequest) -> func.HttpResponse:
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
            status_code=400
        )

    proxy_user = os.getenv("PROXY_USER")
    proxy_pass = os.getenv("PROXY_PASS")

    try:
        ytt_api = YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=proxy_user,
                proxy_password=proxy_pass
            )
        )
        transcript_obj = ytt_api.fetch(video_id)
        transcript = [
            {"start": s.start, "duration": s.duration, "text": s.text}
            for s in transcript_obj.snippets
        ]
        if not transcript:
            logging.warning("transcript_fetch_failed category=transcript_unavailable")
            return func.HttpResponse(
                json.dumps({"error": "transcript_unavailable"}),
                mimetype="application/json",
                status_code=422
            )
        return func.HttpResponse(
            json.dumps({"videoId": video_id, "transcript": transcript}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as error:
        error_code = classify_transcript_error(error)
        logging.warning("transcript_fetch_failed category=%s", error_code)
        status_code = 422 if error_code in {
            "transcript_unavailable", "video_unavailable"
        } else 502
        return func.HttpResponse(
            json.dumps({"error": error_code}),
            mimetype="application/json",
            status_code=status_code
        )
