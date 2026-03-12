import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import ProcessingView from "../components/ProcessingView";

// Mock the api module
vi.mock("../api", () => ({
  getBatchStatus: vi.fn(),
}));

import { getBatchStatus } from "../api";

describe("ProcessingView", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders heading", () => {
    getBatchStatus.mockResolvedValue({
      jobs: [{ id: "j1", filename: "a.pdf", status: "processing" }],
    });

    render(
      <ProcessingView
        batchId="b1"
        onComplete={vi.fn()}
        onSessionExpired={vi.fn()}
      />
    );

    expect(screen.getByText("Processing your files...")).toBeInTheDocument();
  });

  it("displays job filenames after poll", async () => {
    getBatchStatus.mockResolvedValue({
      jobs: [
        { id: "j1", filename: "doc.pdf", status: "processing" },
        { id: "j2", filename: "img.png", status: "queued" },
      ],
    });

    render(
      <ProcessingView
        batchId="b1"
        onComplete={vi.fn()}
        onSessionExpired={vi.fn()}
      />
    );

    // Initial poll fires immediately
    await act(async () => {});

    expect(screen.getByText("doc.pdf")).toBeInTheDocument();
    expect(screen.getByText("img.png")).toBeInTheDocument();
  });

  it("calls onComplete when all jobs are done", async () => {
    const doneJobs = [
      { id: "j1", filename: "a.pdf", status: "done" },
      { id: "j2", filename: "b.pdf", status: "error" },
    ];
    getBatchStatus.mockResolvedValue({ jobs: doneJobs });
    const onComplete = vi.fn();

    render(
      <ProcessingView
        batchId="b1"
        onComplete={onComplete}
        onSessionExpired={vi.fn()}
      />
    );

    await act(async () => {});

    expect(onComplete).toHaveBeenCalledWith(doneJobs);
  });

  it("calls onSessionExpired on SESSION_EXPIRED error", async () => {
    getBatchStatus.mockRejectedValue(new Error("SESSION_EXPIRED"));
    const onSessionExpired = vi.fn();

    render(
      <ProcessingView
        batchId="b1"
        onComplete={vi.fn()}
        onSessionExpired={onSessionExpired}
      />
    );

    await act(async () => {});

    expect(onSessionExpired).toHaveBeenCalled();
  });

  it("polls at 2s interval", async () => {
    getBatchStatus.mockResolvedValue({
      jobs: [{ id: "j1", filename: "a.pdf", status: "processing" }],
    });

    render(
      <ProcessingView
        batchId="b1"
        onComplete={vi.fn()}
        onSessionExpired={vi.fn()}
      />
    );

    // Wait for initial poll to resolve
    await act(async () => {});
    const callsAfterInitial = getBatchStatus.mock.calls.length;
    expect(callsAfterInitial).toBeGreaterThanOrEqual(1);

    // Advance 2s for next poll — should trigger at least one more call
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(getBatchStatus.mock.calls.length).toBeGreaterThan(callsAfterInitial);
  });

  it("displays status text for each job", async () => {
    getBatchStatus.mockResolvedValue({
      jobs: [
        { id: "j1", filename: "a.pdf", status: "processing" },
        { id: "j2", filename: "b.pdf", status: "done" },
        { id: "j3", filename: "c.pdf", status: "error" },
      ],
    });

    render(
      <ProcessingView
        batchId="b1"
        onComplete={vi.fn()}
        onSessionExpired={vi.fn()}
      />
    );

    await act(async () => {});

    expect(screen.getByText("processing")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
  });
});
