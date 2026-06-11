/** 语音转写与会议记录 REST API */
import { api } from "./http.js";

export async function fetchSpeechMeta() {
  return api("/api/v1/speech/meta");
}

export async function transcribeSpeech({ file, language, diarize = true } = {}) {
  const form = new FormData();
  form.append("file", file);
  if (language) form.append("language", language);
  form.append("diarize", diarize ? "true" : "false");
  return api("/api/v1/speech/transcribe", { method: "POST", body: form });
}

export async function summarizeSpeech({ text, style = "minutes", segments = [] } = {}) {
  return api("/api/v1/speech/summarize", {
    method: "POST",
    body: JSON.stringify({ text, style, segments }),
  });
}

export async function saveMeetingRecord(payload) {
  return api("/api/v1/speech/records", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listMeetingRecords({ page = 1, pageSize = 20 } = {}) {
  const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return api(`/api/v1/speech/records?${q}`);
}

export async function fetchMeetingRecord(id) {
  return api(`/api/v1/speech/records/${id}`);
}

export async function deleteMeetingRecord(id) {
  return api(`/api/v1/speech/records/${id}`, { method: "DELETE" });
}
