import { useState, useEffect, useRef } from "react";
import { getBatchStatus } from "../api";

const STATUS_ICONS = {
  queued: "\u23F3",
  processing: "\u2699\uFE0F",
  done: "\u2705",
  error: "\u274C",
};

export default function ProcessingView({ batchId, onComplete, onSessionExpired }) {
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

    poll(); // Initial poll
    intervalRef.current = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      clearInterval(intervalRef.current);
    };
  }, [batchId, onComplete, onSessionExpired]);

  return (
    <div className="mt-10 space-y-3">
      <h3 className="text-lg font-semibold">Processing...</h3>
      {jobs.map((job) => (
        <div
          key={job.id}
          className="flex items-center gap-3 rounded-lg bg-gray-900 p-4"
        >
          <span className="text-xl">{STATUS_ICONS[job.status] || "\u23F3"}</span>
          <div className="flex-1">
            <p className="text-sm font-medium">{job.filename}</p>
            <p className="text-xs text-gray-500 capitalize">{job.status}</p>
          </div>
          {job.status === "processing" && (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
          )}
        </div>
      ))}
    </div>
  );
}
