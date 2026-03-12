import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  healthCheck,
  uploadFiles,
  getBatchStatus,
  previewUrl,
  getPreviewInfo,
  downloadUrl,
  downloadAllUrl,
} from "../api";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("healthCheck", () => {
  it("returns true when server responds ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true });
    expect(await healthCheck()).toBe(true);
    expect(fetch).toHaveBeenCalledWith("/api/health");
  });

  it("returns false on network error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("net"));
    expect(await healthCheck()).toBe(false);
  });

  it("returns false when server responds not ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false });
    expect(await healthCheck()).toBe(false);
  });
});

describe("uploadFiles", () => {
  it("sends FormData with files and returns data", async () => {
    const mockResponse = { batch_id: "b1", jobs: [{ id: "j1" }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    const result = await uploadFiles([file]);

    expect(result).toEqual(mockResponse);
    const [url, opts] = fetch.mock.calls[0];
    expect(url).toBe("/api/upload");
    expect(opts.method).toBe("POST");
    expect(opts.body).toBeInstanceOf(FormData);
  });

  it("throws on error response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: "Too large" }),
    });

    await expect(uploadFiles([])).rejects.toThrow("Too large");
  });
});

describe("getBatchStatus", () => {
  it("returns batch data", async () => {
    const data = { jobs: [{ id: "j1", status: "done" }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    });

    expect(await getBatchStatus("b1")).toEqual(data);
    expect(fetch).toHaveBeenCalledWith("/api/batch/b1");
  });

  it("throws SESSION_EXPIRED on 404", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
    });

    await expect(getBatchStatus("b1")).rejects.toThrow("SESSION_EXPIRED");
  });

  it("throws generic error on other failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 500,
    });

    await expect(getBatchStatus("b1")).rejects.toThrow("Failed to fetch status");
  });
});

describe("previewUrl", () => {
  it("returns base URL for processed page 0", () => {
    expect(previewUrl("j1")).toBe("/api/preview/j1");
  });

  it("adds type=original for original", () => {
    expect(previewUrl("j1", "original")).toBe("/api/preview/j1?type=original");
  });

  it("adds page param for page > 0", () => {
    expect(previewUrl("j1", "processed", 2)).toBe("/api/preview/j1?page=2");
  });

  it("adds both params for original page > 0", () => {
    expect(previewUrl("j1", "original", 3)).toBe(
      "/api/preview/j1?type=original&page=3"
    );
  });
});

describe("getPreviewInfo", () => {
  it("returns page count from server", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ page_count: 5 }),
    });

    expect(await getPreviewInfo("j1")).toEqual({ page_count: 5 });
  });

  it("defaults to page_count 1 on error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false });
    expect(await getPreviewInfo("j1")).toEqual({ page_count: 1 });
  });
});

describe("downloadUrl / downloadAllUrl", () => {
  it("returns correct download URL", () => {
    expect(downloadUrl("j1")).toBe("/api/download/j1");
  });

  it("returns correct download-all URL", () => {
    expect(downloadAllUrl("b1")).toBe("/api/download-all/b1");
  });
});
