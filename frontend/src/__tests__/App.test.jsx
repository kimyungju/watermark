import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

vi.mock("../api", () => ({
  healthCheck: vi.fn().mockResolvedValue(true),
  uploadFiles: vi.fn(),
  getBatchStatus: vi.fn(),
  previewUrl: (id, type, page) => `/preview/${id}`,
  downloadUrl: (id) => `/download/${id}`,
  downloadAllUrl: (id) => `/download-all/${id}`,
  getPreviewInfo: vi.fn().mockResolvedValue({ page_count: 1 }),
}));

import { healthCheck, uploadFiles, getBatchStatus, getPreviewInfo } from "../api";

// Mock ResizeObserver for BeforeAfterSlider
globalThis.ResizeObserver = class {
  constructor(cb) { this._cb = cb; }
  observe(el) { this._cb([{ contentRect: { width: 400 } }]); }
  disconnect() {}
};

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Re-apply default mock return values
    healthCheck.mockResolvedValue(true);
    getPreviewInfo.mockResolvedValue({ page_count: 1 });
  });

  it("renders upload view initially", () => {
    render(<App />);
    expect(screen.getByText("Remove watermarks")).toBeInTheDocument();
    expect(
      screen.getByText("Drop files here or click to browse")
    ).toBeInTheDocument();
  });

  it("shows uploading spinner during upload", async () => {
    // Make uploadFiles hang
    uploadFiles.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();

    render(<App />);

    const input = document.querySelector('input[type="file"]');
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    await user.upload(input, file);

    expect(screen.getByText("Uploading...")).toBeInTheDocument();
  });

  it("shows upload error on failure", async () => {
    uploadFiles.mockRejectedValue(new Error("Server down"));
    const user = userEvent.setup();

    render(<App />);

    const input = document.querySelector('input[type="file"]');
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    await user.upload(input, file);

    await act(async () => {});
    expect(screen.getByText("Server down")).toBeInTheDocument();
  });

  it("transitions to processing view after upload", async () => {
    uploadFiles.mockResolvedValue({
      batch_id: "b1",
      jobs: [{ id: "j1", filename: "test.pdf", status: "processing" }],
    });
    getBatchStatus.mockResolvedValue({
      jobs: [{ id: "j1", filename: "test.pdf", status: "processing" }],
    });
    const user = userEvent.setup();

    render(<App />);

    const input = document.querySelector('input[type="file"]');
    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    await user.upload(input, file);

    await act(async () => {});
    expect(screen.getByText("Processing your files...")).toBeInTheDocument();
  });
});
