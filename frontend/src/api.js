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

export function previewUrl(jobId, type = "processed", page = 0) {
  const params = new URLSearchParams();
  if (type === "original") params.set("type", "original");
  if (page > 0) params.set("page", page);
  const qs = params.toString();
  return `${API_BASE}/preview/${jobId}${qs ? `?${qs}` : ""}`;
}

export async function getPreviewInfo(jobId) {
  try {
    const res = await fetch(`${API_BASE}/preview/${jobId}/info`);
    if (!res.ok) {
      console.warn(`Preview info failed for ${jobId}: ${res.status}`);
      return { page_count: 1 };
    }
    return res.json();
  } catch (err) {
    console.warn(`Preview info error for ${jobId}:`, err);
    return { page_count: 1 };
  }
}

export function downloadUrl(jobId) {
  return `${API_BASE}/download/${jobId}`;
}

export function downloadAllUrl(batchId) {
  return `${API_BASE}/download-all/${batchId}`;
}
