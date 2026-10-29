# Transcript Request Analytics (TranscriberAPI2)

This feature is opt-in. Set `TRANSCRIPT_ANALYTICS_ENABLED=true` only on the **TranscriberAPI2** Function App. When absent or false, `GetTranscript` follows its legacy path and does not initialize the OTel distro or emit custom events. The `TranscriberAPI` workflow and settings are not changed.

## API2 Application Settings

Keep the existing `APPLICATIONINSIGHTS_CONNECTION_STRING` value on TranscriberAPI2. Add/confirm these settings only on TranscriberAPI2:

| Setting | Value |
| --- | --- |
| `TRANSCRIPT_ANALYTICS_ENABLED` | `true` |
| `PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY` | `true` |
| `AzureFunctionsJobHost__telemetryMode` | `OpenTelemetry` |

`AzureFunctionsJobHost__telemetryMode` is the app-setting override for `host.json`'s `telemetryMode`; it leaves the shared `host.json` unchanged. The API2 workflow installs `requirements-api2.txt`, which contains the Microsoft OpenTelemetry Python distro. No connection string is added to source or workflow files.

Do not set `TRANSCRIPT_ANALYTICS_ENABLED` on TranscriberAPI. Keep Application Insights' default client-IP masking enabled; do not add `client.address` or IP/user identifiers to custom dimensions.

## Event Schema

The Function emits one `transcript_request_completed` custom event from a `finally` path for each invocation when enabled:

- `video_id`
- `outcome`: `success` or `failure`
- `error_type`: empty on success
- `duration_ms`
- `caption_type`: `manual`, `auto`, or `unknown`
- `length_bucket`: `<5m`, `5-15m`, `15-60m`, `60m+`, or `unknown`

Duration/length are approximate, derived from the last transcript snippet's start plus duration. Events contain no transcript text, feedback text, or email. The request keeps the existing `GET /api/GetTranscript?videoId=...` format. The video ID is therefore present in Application Insights' automatic request URL telemetry as well as the approved custom event.

The API2 error mapping is:

| Error type | Library/network exceptions |
| --- | --- |
| `invalid_url` | Missing/malformed ID; `InvalidVideoId` |
| `transcript_unavailable` | `NoTranscriptFound`, `TranscriptsDisabled`, `TranslationLanguageNotAvailable` |
| `video_unavailable` | `VideoUnavailable`, `VideoUnplayable`, `AgeRestricted` |
| `rate_limited` | `TooManyRequests`, `RateLimitExceeded`, HTTP 429 including wrapped `YouTubeRequestFailed` with a 429 reason/status |
| `proxy_blocked` | `RequestBlocked`, `IpBlocked`, `ProxyError` |
| `timeout` | `Timeout`, `ConnectTimeout`, `ReadTimeout`, `TimeoutError` |
| `network_error` | `ConnectionError`, `ConnectionResetError`, `NewConnectionError` |
| `invalid_response` | `YouTubeDataUnparsable`, malformed transcript response |
| `upstream_error` | Other `YouTubeRequestFailed` |
| `unknown` | Other exceptions |

`RequestBlocked` and `IpBlocked` are the transcript library's IP/proxy-block exceptions. HTTP 429 and rate-limit exception names map to `rate_limited`. Classification examines exception types/status/reason only; it never logs the raw exception message.

## KQL

Run in the Application Insights resource's **Logs**. The first query checks whether event rows have a country field and whether they correlate to request rows:

```kusto
let events = customEvents
| where timestamp > ago(7d)
| where name == "transcript_request_completed"
| project timestamp, operation_Id, eventCountry = tostring(client_CountryOrRegion);
let requestsByOperation = requests
| where timestamp > ago(7d)
| summarize request_id = take_any(id), requestCountry = take_any(client_CountryOrRegion)
    by operation_Id;
events
| join kind=leftouter requestsByOperation on operation_Id
| summarize events = count(),
            eventsWithCountry = countif(isnotempty(eventCountry)),
            eventsMatchingRequest = countif(isnotempty(request_id)),
            eventsWithJoinedCountry = countif(isnotempty(requestCountry))
```

The workspace/resource is not accessible from this repo, so this correlation has **not** been verified against live data. If `eventsWithCountry` is zero but `eventsWithJoinedCountry` is nonzero, use the correlated-request country as below. If `eventsMatchingRequest` is zero, the join is not working in that resource; check whether both tables have `operation_Id` populated before using the country breakdown.

```kusto
let requestCountry = requests
| where timestamp > ago(30d)
| summarize country = take_any(client_CountryOrRegion) by operation_Id;
customEvents
| where timestamp > ago(30d)
| where name == "transcript_request_completed"
| join kind=leftouter requestCountry on operation_Id
| extend country = coalesce(tostring(client_CountryOrRegion), country, "unknown")
| extend local_time = datetime_utc_to_local(timestamp, "Asia/Kolkata")
| extend hour_ist = datetime_part("hour", local_time)
| extend video_id = tostring(customDimensions["video_id"])
| summarize requests = sum(itemCount) by country, hour_ist, video_id
| sort by country asc, hour_ist asc, requests desc
```

This returns the country/hour/video aggregates sorted by volume; apply a Top 10 filter per country and IST hour in the query/chart. If your tenant accepts the Windows timezone ID, `India Standard Time` can be used instead of `Asia/Kolkata`.

```kusto
// Success rate per day
customEvents
| where name == "transcript_request_completed"
| extend outcome = tostring(customDimensions["outcome"])
| summarize total = sum(itemCount),
            successes = sumif(itemCount, outcome == "success")
    by day = bin(timestamp, 1d)
| extend success_rate_pct = 100.0 * successes / total
| order by day asc
```

```kusto
// Failures by error type
customEvents
| where name == "transcript_request_completed"
| where tostring(customDimensions["outcome"]) == "failure"
| summarize failures = sum(itemCount)
    by error_type = tostring(customDimensions["error_type"])
| order by failures desc
```

```kusto
// p50/p95 duration in milliseconds
customEvents
| where name == "transcript_request_completed"
| summarize percentiles(todouble(customDimensions["duration_ms"]), 50, 95)
    by bin(timestamp, 1d)
```

```kusto
// Successful requests by caption type and transcript length
customEvents
| where name == "transcript_request_completed"
| where tostring(customDimensions["outcome"]) == "success"
| summarize requests = sum(itemCount)
    by caption_type = tostring(customDimensions["caption_type"]),
       length_bucket = tostring(customDimensions["length_bucket"])
| order by requests desc
```

## Production Checklist

- Set the three API2 settings above and retain the existing connection string.
- Confirm `TranscriberAPI2` is linked to the intended Application Insights resource and default IP masking remains enabled.
- Test one successful video, one no-captions video, one invalid ID, one blocked/proxy case, and one 429 case; verify one custom event per HTTP request with the dimensions above.
- Confirm no custom event dimensions contain feedback text, email, transcript text, IP, or session ID.
- Run the country/correlation query above against live data; verify the operation join match count before relying on joined country.
- **Rollback:** set `TRANSCRIPT_ANALYTICS_ENABLED=false` or remove it from TranscriberAPI2 and restart the app. The Function immediately uses its legacy non-analytics path; revert the API2-only workflow/package change later if desired.

## Shared-Repository Deployment Caveat

Both Function App workflows trigger on a push to this repo's `main`. The API2 dependency and telemetry are gated so TranscriberAPI remains behaviorally unchanged when its analytics setting is absent, and its workflow is untouched. However, pushing shared source to `main` still runs the TranscriberAPI deployment workflow. To avoid deploying anything to the unused app, keep these changes on a branch and use **Actions > Build and deploy Python project to Azure Function App - TranscriberAPI2 > Run workflow** on that branch. Do not push this change to `main` if even a no-op-behavior redeployment of TranscriberAPI is unacceptable.
