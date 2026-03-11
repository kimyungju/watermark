import { useState, useEffect, useRef } from "react";
import { getBatchStatus } from "../api";

function StatusIndicator({ status }) {
  if (status === "processing") {
    return (
      <div className="relative flex h-5 w-5 items-center justify-center">
        <div
          className="absolute h-5 w-5 rounded-full border-2 border-[var(--color-accent)] border-t-transparent"
          style={{ animation: "spin-slow 0.8s linear infinite" }}
        />
        <div className="h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]" />
      </div>
    );
  }

  if (status === "done") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-success)]">
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          stroke="var(--color-base)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="2 5.5 4 7.5 8 3" />
        </svg>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-error)]">
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          stroke="var(--color-base)"
          strokeWidth="1.5"
          strokeLinecap="round"
        >
          <path d="M3 3l4 4M7 3l-4 4" />
        </svg>
      </div>
    );
  }

  // queued
  return (
    <div className="flex h-5 w-5 items-center justify-center">
      <div className="h-2 w-2 rounded-full bg-[var(--color-text-dim)]" />
    </div>
  );
}

export default function ProcessingView({
  batchId,
  onComplete,
  onSessionExpired,
}) {
  const [jobs, setJobs] = useState([]);
  const intervalRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getBatchStatus(batchId);
        if (cancelled) return;
        setJobs(data.jobs);

        const allDone = data.jobs.every(
          (j) => j.status === "done" || j.status === "error"
        );
        if (allDone) {
          clearInterval(intervalRef.current);
          onComplete(data.jobs);
        }
      } catch (err) {
        if (err.message === "SESSION_EXPIRED") {
          clearInterval(intervalRef.current);
          onSessionExpired();
        }
      }
    }

    poll();
    intervalRef.current = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      clearInterval(intervalRef.current);
    };
  }, [batchId, onComplete, onSessionExpired]);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="animate-fade-up text-center">
        <h3
          className="text-2xl tracking-tight"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Processing your files...
        </h3>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">
          This usually takes a few seconds
        </p>
      </div>

      <div className="mt-8 space-y-2">
        {jobs.map((job, i) => (
          <div
            key={job.id}
            className="animate-fade-up flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
            style={{ animationDelay: `${i * 0.06}s` }}
          >
            <StatusIndicator status={job.status} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-[var(--color-text)]">
                {job.filename}
              </p>
            </div>
            <span className="text-xs capitalize text-[var(--color-text-dim)]">
              {job.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
