# TranscriptX Feedback Storage Setup

The browser submits feedback only to the Azure Function endpoint `/api/Feedback`. The Function validates and rate-limits the submission, then forwards it to this Apps Script web app. The browser never receives the Apps Script URL or shared secret. The Function sends the shared secret as the JSON POST body field `secret`; it is not added to the Apps Script URL or its query string.

## Google Sheet

1. Create a spreadsheet, for example `TranscriptX Feedback`.
2. Rename the worksheet tab to `feedback` (lowercase).
3. Put these headers in row 1, in this exact order. The Apps Script can create them when row 1 is empty, but setting them explicitly makes the schema visible:

   `id`, `created_at`, `source`, `category`, `use_case`, `use_case_other`, `helpful`, `message`, `email`, `page_path`, `user_agent`, `viewport_width`, `error_type`, `video_url`

`video_url` is blank unless the visitor explicitly opts in. There are no IP-address, session-token, honeypot, or secret columns.

## Apps Script Web App

1. In the spreadsheet, choose **Extensions > Apps Script**.
2. Replace the editor contents with [`GoogleAppsScript.gs`](GoogleAppsScript.gs) and save.
3. In Apps Script, open **Project Settings > Script Properties** and add:
   - `FEEDBACK_SPREADSHEET_ID`: the ID from the spreadsheet URL between `/d/` and `/edit`.
   - `FEEDBACK_SHARED_SECRET`: a newly generated random secret. Generate one locally with `openssl rand -hex 32`; enter it directly into Script Properties and Azure settings. Do not put it in source control or send it in chat.
4. Choose **Deploy > New deployment**. Select the gear icon, choose **Web app**, set **Execute as** to **Me**, and set **Who has access** to **Anyone**. Deploy and authorize the requested Sheets access.
5. Copy the deployed Web app URL ending in `/exec`. Keep it private. If you change the script later, create a new version under **Deploy > Manage deployments > Edit > New version**.

The public access setting is needed for the Azure Function to invoke the web app without a Google login. The shared secret is checked by the script before any row is written. Do not log or expose the request body in Apps Script.

## Frontend API URL

The frontend uses the same base URL for transcript fetches and feedback submissions. Set `VITE_API_BASE_URL` as a GitHub Actions **repository variable** under **Settings > Secrets and variables > Actions > Variables**. The UI workflow passes it into the Vite production build.

Production value:

`VITE_API_BASE_URL=https://transcriberapi2-hahuhgd4caayd2by.centralindia-01.azurewebsites.net/api`

For local UI development, copy `.env.example` to `.env.local`. It points at a locally running Function host:

`VITE_API_BASE_URL=http://127.0.0.1:7071/api`

`VITE_API_BASE_URL` is public configuration compiled into the frontend, not a secret. Do not put Apps Script URLs or secrets in Vite variables.

## Function App Settings

In Azure Portal, open **TranscriberAPI2 > Settings > Environment variables** and configure these application settings:

| Exact setting name | Production value / purpose |
| --- | --- |
| `FEEDBACK_APPS_SCRIPT_URL` | Private deployed Apps Script `/exec` URL. |
| `FEEDBACK_APPS_SCRIPT_SECRET` | Same random value as Apps Script property `FEEDBACK_SHARED_SECRET`. |
| `FEEDBACK_ALLOWED_ORIGINS` | Exactly `https://transcriptsx.com` in production. |
| `PROXY_USER` | Existing Webshare proxy username used by the transcript function. |
| `PROXY_PASS` | Existing Webshare proxy password used by the transcript function. |
| `FUNCTIONS_WORKER_RUNTIME` | `python` (Azure Functions runtime setting). |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` (Azure Functions runtime setting). |
| `AzureWebJobsStorage` | Storage connection string used by the Functions host; retain the value provisioned for this app. |

`TranscriberAPI2` is the backend used by the website. The repository also deploys to `TranscriberAPI`; set the feedback settings there only if that app should accept feedback too. Never commit the Apps Script URL or shared secret.

Azure Portal **Function App > Settings > CORS** should list only `https://transcriptsx.com` in production. Do not add localhost or `*` there.

For local Functions development, put the local-only setting in your ignored `local.settings.json` (the repository `.gitignore` excludes it):

```json
{
   "IsEncrypted": false,
   "Values": {
      "AzureWebJobsStorage": "UseDevelopmentStorage=true",
      "FUNCTIONS_WORKER_RUNTIME": "python",
      "FEEDBACK_ALLOWED_ORIGINS": "http://localhost:8080,http://127.0.0.1:8080"
   }
}
```

Add local `FEEDBACK_APPS_SCRIPT_URL`, `FEEDBACK_APPS_SCRIPT_SECRET`, `PROXY_USER`, and `PROXY_PASS` values only if you need local end-to-end submissions or transcript fetching. The production allowlist defaults to `https://transcriptsx.com`; localhost is accepted only when explicitly configured in local settings.

## Apps Script Properties

The Apps Script project stores these values in **Project Settings > Script Properties**:

| Exact property name | Purpose |
| --- | --- |
| `FEEDBACK_SPREADSHEET_ID` | Destination spreadsheet ID. |
| `FEEDBACK_SHARED_SECRET` | Shared secret validated against the Function's JSON POST body field `secret`. |

These are Google Apps Script properties, not Azure app settings. The Azure Function does not put the secret in any URL.

## Privacy and Logs

The feedback Function does not log request bodies, emails, message text, the session token, or video URLs. It uses the session token only as an in-memory rate-limit key; neither it nor an IP address is forwarded to the sheet. Its URL has no feedback fields in the query string. Apps Script writes a fixed list of columns, does not call `Logger`, and returns generic errors without echoing submitted values. Azure/Application Insights may retain ordinary request telemetry such as endpoint, status, and duration, but the endpoint must not include user data in its URL. Do not enable custom body/header logging for this Function.

Both the Azure Function and Apps Script prefix text values beginning with spreadsheet formula characters (including after leading whitespace) with an apostrophe before writing. This prevents submitted text from being evaluated as a formula.

## Transcript Failure Monitoring

The transcript Function records only a category when a fetch fails: `transcript_unavailable`, `video_unavailable`, or `upstream_error`. It does not log the video ID, URL, transcript, upstream exception text, or stack trace. The browser displays friendly error messages and does not write diagnostic details to the console.

To retain and query these events, enable Application Insights for **TranscriberAPI2** in Azure. Azure may configure the Function App's `APPLICATIONINSIGHTS_CONNECTION_STRING` setting automatically; if configuring it yourself, add that exact setting in Azure App Settings. The telemetry connection string is not a Vite/frontend variable. In Application Insights **Logs**, run:

```kusto
traces
| where message startswith "transcript_fetch_failed category="
| parse message with "transcript_fetch_failed category=" category:string
| summarize failures = count() by category, bin(timestamp, 1d)
| order by timestamp desc
```

This gives you daily counts by failure category without retaining the exception details. Verify the query with a controlled test video that has no captions after deployment.

## Reading Feedback

Open the `feedback` worksheet in the spreadsheet. Filter the `source` column (`tab`, `survey`, or `failure`) to review each type. Only people with access to the spreadsheet can read the responses.
