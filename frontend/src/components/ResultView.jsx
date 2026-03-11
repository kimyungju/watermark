import BeforeAfterSlider from "./BeforeAfterSlider";
import { previewUrl, downloadUrl, downloadAllUrl } from "../api";

function DownloadIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7 2v7.5" />
      <polyline points="3.5 6.5 7 10 10.5 6.5" />
      <path d="M2 11.5h10" />
    </svg>
  );
}

export default function ResultView({ jobs, batchId, onReset }) {
  const doneJobs = jobs.filter((j) => j.status === "done");
  const errorJobs = jobs.filter((j) => j.status === "error");

  return (
    <div className="animate-fade-up">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3
            className="text-2xl tracking-tight"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {doneJobs.length === 1 ? "Your file is ready" : "Your files are ready"}
          </h3>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {doneJobs.length} of {jobs.length} processed
          </p>
        </div>
        <div className="flex gap-2">
          {doneJobs.length > 1 && (
            <a
              href={downloadAllUrl(batchId)}
              className="inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium transition-all duration-200"
              style={{
                background: "var(--color-accent)",
                color: "var(--color-base)",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "var(--color-accent-hover)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "var(--color-accent)")
              }
            >
              <DownloadIcon />
              Download All
            </a>
          )}
          <button
            onClick={onReset}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2.5 text-sm font-medium text-[var(--color-text-muted)] transition-all duration-200 hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)]"
          >
            Remove more
          </button>
        </div>
      </div>

      {/* Errors */}
      {errorJobs.length > 0 && (
        <div className="mt-5 rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 px-4 py-3 text-sm text-[var(--color-error)]">
          {errorJobs.map((job) => (
            <p key={job.id}>
              {job.filename}: {job.error || "Processing failed"}
            </p>
          ))}
        </div>
      )}

      {/* Result cards */}
      <div className="mt-8 space-y-8">
        {doneJobs.map((job, i) => (
          <div
            key={job.id}
            className="animate-fade-up overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]"
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            {/* Card header */}
            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-3.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--color-text)]">
                  {job.filename}
                </p>
                {job.watermark_detected === false && (
                  <p className="mt-0.5 text-xs text-[var(--color-warning)]">
                    No watermark detected &mdash; original file returned
                  </p>
                )}
                {job.watermark_detected === true && (
                  <p className="mt-0.5 text-xs text-[var(--color-success)]">
                    Watermark removed
                  </p>
                )}
              </div>
              <a
                href={downloadUrl(job.id)}
                className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200"
                style={{
                  background: "var(--color-accent)",
                  color: "var(--color-base)",
                }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background =
                    "var(--color-accent-hover)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "var(--color-accent)")
                }
              >
                <DownloadIcon />
                Download
              </a>
            </div>

            {/* Before/After comparison */}
            {job.watermark_detected !== false && (
              <div className="p-4">
                <BeforeAfterSlider
                  beforeSrc={previewUrl(job.id, "original")}
                  afterSrc={previewUrl(job.id)}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
