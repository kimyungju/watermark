import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ResultView from "../components/ResultView";

vi.mock("../api", () => ({
  previewUrl: (id, type, page) => `/api/preview/${id}?type=${type}&page=${page}`,
  downloadUrl: (id) => `/api/download/${id}`,
  downloadAllUrl: (id) => `/api/download-all/${id}`,
  getPreviewInfo: vi.fn().mockResolvedValue({ page_count: 1 }),
}));

// Mock ResizeObserver for BeforeAfterSlider
globalThis.ResizeObserver = class {
  constructor(cb) { this._cb = cb; }
  observe(el) { this._cb([{ contentRect: { width: 400 } }]); }
  disconnect() {}
};

const doneJob = {
  id: "j1",
  filename: "test.pdf",
  status: "done",
  watermark_detected: true,
};

const noWatermarkJob = {
  id: "j2",
  filename: "clean.pdf",
  status: "done",
  watermark_detected: false,
};

const errorJob = {
  id: "j3",
  filename: "bad.pdf",
  status: "error",
  error: "Processing failed",
};

describe("ResultView", () => {
  it("renders single file heading", async () => {
    render(<ResultView jobs={[doneJob]} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    expect(screen.getByText("Your file is ready")).toBeInTheDocument();
  });

  it("renders plural heading for multiple files", async () => {
    render(
      <ResultView jobs={[doneJob, { ...doneJob, id: "j4" }]} batchId="b1" onReset={vi.fn()} />
    );
    await act(async () => {});
    expect(screen.getByText("Your files are ready")).toBeInTheDocument();
  });

  it("shows filename and download link", async () => {
    render(<ResultView jobs={[doneJob]} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
    const link = screen.getByText("Download").closest("a");
    expect(link).toHaveAttribute("href", "/api/download/j1");
  });

  it("shows watermark removed indicator", async () => {
    render(<ResultView jobs={[doneJob]} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    expect(screen.getByText("Watermark removed")).toBeInTheDocument();
  });

  it("shows no-watermark message for clean files", async () => {
    render(<ResultView jobs={[noWatermarkJob]} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    expect(
      screen.getByText(/No watermark detected/)
    ).toBeInTheDocument();
  });

  it("shows Download All button for multiple done jobs", async () => {
    const jobs = [doneJob, { ...doneJob, id: "j4", filename: "b.pdf" }];
    render(<ResultView jobs={jobs} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    const allLink = screen.getByText("Download All").closest("a");
    expect(allLink).toHaveAttribute("href", "/api/download-all/b1");
  });

  it("does not show Download All for single file", async () => {
    render(<ResultView jobs={[doneJob]} batchId="b1" onReset={vi.fn()} />);
    await act(async () => {});
    expect(screen.queryByText("Download All")).not.toBeInTheDocument();
  });

  it("shows error jobs", async () => {
    render(
      <ResultView jobs={[doneJob, errorJob]} batchId="b1" onReset={vi.fn()} />
    );
    await act(async () => {});
    expect(screen.getByText(/bad\.pdf: Processing failed/)).toBeInTheDocument();
  });

  it("calls onReset when Remove more is clicked", async () => {
    const onReset = vi.fn();
    const user = userEvent.setup();
    render(<ResultView jobs={[doneJob]} batchId="b1" onReset={onReset} />);
    await act(async () => {});

    await user.click(screen.getByText("Remove more"));
    expect(onReset).toHaveBeenCalled();
  });

  it("shows processed count", async () => {
    render(
      <ResultView jobs={[doneJob, errorJob]} batchId="b1" onReset={vi.fn()} />
    );
    await act(async () => {});
    expect(screen.getByText("1 of 2 processed")).toBeInTheDocument();
  });
});
