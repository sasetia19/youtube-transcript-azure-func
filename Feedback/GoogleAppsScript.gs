const SHEET_NAME = "feedback";
const HEADERS = [
  "id",
  "created_at",
  "source",
  "category",
  "use_case",
  "use_case_other",
  "helpful",
  "message",
  "email",
  "page_path",
  "user_agent",
  "viewport_width",
  "error_type",
  "video_url",
];

function doPost(event) {
  const lock = LockService.getScriptLock();
  let hasLock = false;

  try {
    hasLock = lock.tryLock(10000);
    if (!hasLock) return jsonResponse({ ok: false });

    const properties = PropertiesService.getScriptProperties();
    const expectedSecret = properties.getProperty("FEEDBACK_SHARED_SECRET");
    const spreadsheetId = properties.getProperty("FEEDBACK_SPREADSHEET_ID");
    const payload = JSON.parse(event.postData.contents || "{}");

    if (!expectedSecret || payload.secret !== expectedSecret || !spreadsheetId) {
      return jsonResponse({ ok: false });
    }
    if (!payload.id || !payload.created_at || !["tab", "survey", "failure"].includes(payload.source)) {
      return jsonResponse({ ok: false });
    }

    const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);
    if (!sheet) return jsonResponse({ ok: false });

    const firstRow = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
    if (firstRow.every((value) => value === "")) {
      sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    } else if (HEADERS.some((header, index) => firstRow[index] !== header)) {
      return jsonResponse({ ok: false });
    }

    const row = HEADERS.map((header) => {
      const value = payload[header];
      return sanitizeCell(value === undefined || value === null ? "" : value);
    });
    sheet.appendRow(row);
    return jsonResponse({ ok: true });
  } catch (_) {
    return jsonResponse({ ok: false });
  } finally {
    if (hasLock) lock.releaseLock();
  }
}

function sanitizeCell(value) {
  if (typeof value !== "string") return value;
  if (/^[ \t\r\n]*[=+\-@\t\r]/.test(value)) return "'" + value;
  return value;
}

function jsonResponse(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
