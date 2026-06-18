import { getAuth } from "firebase/auth";

function sessionKey(): string {
  const uid = getAuth().currentUser?.uid ?? "anonymous";
  return `abc-analysis-upload-ids-${uid}`;
}

export function loadAbcAnalysisUploadIds(): string[] {
  try {
    const raw = sessionStorage.getItem(sessionKey());
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function saveAbcAnalysisUploadIds(ids: string[]): void {
  const unique = [...new Set(ids.filter((id) => id && !id.startsWith("pending-")))];
  sessionStorage.setItem(sessionKey(), JSON.stringify(unique));
}

export function appendAbcAnalysisUploadId(uploadId: string): void {
  if (!uploadId || uploadId.startsWith("pending-")) return;
  const ids = loadAbcAnalysisUploadIds();
  if (!ids.includes(uploadId)) {
    saveAbcAnalysisUploadIds([...ids, uploadId]);
  }
}
