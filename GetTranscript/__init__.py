import azure.functions as func
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import os
import json

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
            json.dumps({"error": "Missing 'videoId' parameter"}),
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
        return func.HttpResponse(
            json.dumps({"videoId": video_id, "transcript": transcript}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )
