const API_BASE = "/api";

export async function healthCheck() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadFiles(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function getBatchStatus(batchId) {
  const res = await fetch(`${API_BASE}/batch/${batchId}`);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("SESSION_EXPIRED");
    }
    throw new Error("Failed to fetch status");
  }
  return res.json();
}

export function previewUrl(jobId, type = "processed") {
  const param = type === "original" ? "?type=original" : "";
  return `${API_BASE}/preview/${jobId}${param}`;
}

export function downloadUrl(jobId) {
  return `${API_BASE}/download/${jobId}`;
}

export function downloadAllUrl(batchId) {
  return `${API_BASE}/download-all/${batchId}`;
}
