/** 语音合成 REST API */
import { getApiBase, getToken, rejectHttpFailure, UPLOAD_API_TIMEOUT_MS } from "./http.js";
import { downloadBlob } from "../utils/downloadBlob.js";

export async function fetchTextToSpeechMeta() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(`${getApiBase()}/api/v1/text-to-speech/meta`, {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal: controller.signal,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) rejectHttpFailure(res, json);
    return json?.data;
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error("加载语音合成配置超时，请检查网络或 API 服务");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function synthesizeTextToSpeech({
  text,
  voiceId = "alex",
  emotion = null,
  speed = 1,
  responseFormat = "mp3",
} = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_API_TIMEOUT_MS);
  try {
    const res = await fetch(`${getApiBase()}/api/v1/text-to-speech/synthesize`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getToken()}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        voice_id: voiceId,
        emotion: emotion || null,
        speed,
        response_format: responseFormat,
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      rejectHttpFailure(res, json);
    }
    const blob = await res.blob();
    const disp = res.headers.get("Content-Disposition") || "";
    const match = disp.match(/filename="?([^";]+)"?/);
    const filename = match ? match[1] : `speech.${responseFormat || "mp3"}`;
    return { blob, filename, contentType: res.headers.get("Content-Type") || blob.type };
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error("语音合成超时，请缩短文本后重试");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function downloadSpeechBlob(blob, filename) {
  downloadBlob(blob, filename);
}
