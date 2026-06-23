const STORAGE_KEY = "platform.releaseHighlightsAck";

export function getAcknowledgedReleaseVersion() {
  try {
    return String(localStorage.getItem(STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function acknowledgeReleaseVersion(version) {
  const ver = String(version || "").trim();
  if (!ver) return;
  try {
    localStorage.setItem(STORAGE_KEY, ver);
  } catch {
    /* ignore quota / private mode */
  }
}

export function shouldShowReleaseHighlights(version) {
  const ver = String(version || "").trim();
  if (!ver) return false;
  return getAcknowledgedReleaseVersion() !== ver;
}
