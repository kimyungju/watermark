import { useState, useEffect, useCallback } from "react";
import { healthCheck, uploadFiles } from "./api";
import UploadZone from "./components/UploadZone";
import ProcessingView from "./components/ProcessingView";
import ResultView from "./components/ResultView";

function App() {
  const [view, setView] = useState("upload");
  const [batchId, setBatchId] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [uploadError, setUploadError] = useState(null);
  const [serverErrors, setServerErrors] = useState([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    healthCheck();
  }, []);

  const handleUpload = useCallback(async (files) => {
    setUploadError(null);
    setServerErrors([]);
    setUploading(true);

    try {
      const data = await uploadFiles(files);
      if (data.errors?.length > 0) {
        setServerErrors(data.errors);
      }
      if (data.jobs.length > 0) {
        setBatchId(data.batch_id);
        setJobs(data.jobs);
        setView("processing");
      }
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }, []);

  const handleComplete = useCallback((completedJobs) => {
    setJobs(completedJobs);
    setView("result");
  }, []);

  const handleSessionExpired = useCallback(() => {
    setUploadError("Session expired — please re-upload your files");
    setView("upload");
  }, []);

  const handleReset = useCallback(() => {
    setView("upload");
    setBatchId(null);
    setJobs([]);
    setUploadError(null);
    setServerErrors([]);
  }, []);

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Ambient background gradient */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div
          className="absolute top-[-20%] left-[10%] h-[600px] w-[600px] rounded-full opacity-[0.04]"
          style={{
            background:
              "radial-gradient(circle, var(--color-accent) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute right-[5%] bottom-[10%] h-[400px] w-[400px] rounded-full opacity-[0.03]"
          style={{
            background:
              "radial-gradient(circle, var(--color-accent) 0%, transparent 70%)",
          }}
        />
      </div>

      <header className="border-b border-[var(--color-border)] px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <button
            onClick={handleReset}
            className="group flex items-center gap-2 bg-transparent border-none cursor-pointer"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-accent)] text-[var(--color-base)]">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M2 8h12M8 2v12M5 5l6 6M11 5l-6 6"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  opacity="0.3"
                />
                <path
                  d="M3 3L13 13M13 3L3 13"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <span
              className="text-lg tracking-tight text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors"
              style={{ fontFamily: "var(--font-display)" }}
            >
              WatermarkOff
            </span>
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        {view === "upload" && (
          <div className="mx-auto max-w-2xl">
            <div className="text-center">
              <h2
                className="animate-fade-up text-4xl leading-tight tracking-tight sm:text-5xl"
                style={{ fontFamily: "var(--font-display)" }}
              >
                Remove watermarks
                <br />
                <span className="italic text-[var(--color-accent)]">
                  instantly
                </span>
              </h2>
              <p className="animate-fade-up stagger-1 mt-4 text-base text-[var(--color-text-muted)]">
                Drop your PDFs and images. We detect and erase watermarks
                automatically.
              </p>
            </div>

            <div className="animate-fade-up stagger-2">
              <UploadZone onUpload={handleUpload} disabled={uploading} />
            </div>

            {uploading && (
              <div className="animate-fade-in mt-6 flex items-center justify-center gap-2 text-sm text-[var(--color-text-muted)]">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
                Uploading...
              </div>
            )}

            {uploadError && (
              <div className="animate-fade-up mt-5 rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 px-4 py-3 text-sm text-[var(--color-error)]">
                {uploadError}
              </div>
            )}

            {serverErrors.length > 0 && (
              <div className="animate-fade-up mt-5 rounded-xl border border-[var(--color-warning)]/20 bg-[var(--color-warning)]/5 px-4 py-3 text-sm text-[var(--color-warning)]">
                {serverErrors.map((e, i) => (
                  <p key={i}>
                    {e.filename}: {e.error}
                  </p>
                ))}
              </div>
            )}

            {/* Features strip */}
            <div className="animate-fade-up stagger-3 mt-16 grid grid-cols-3 gap-6 text-center">
              {[
                {
                  icon: (
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 20 20"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    >
                      <path d="M10 2v16M2 10h16" />
                    </svg>
                  ),
                  label: "No signup required",
                },
                {
                  icon: (
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 20 20"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    >
                      <rect x="3" y="4" width="14" height="12" rx="2" />
                      <path d="M3 8h14" />
                    </svg>
                  ),
                  label: "PDFs & images",
                },
                {
                  icon: (
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 20 20"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    >
                      <path d="M13 2H6a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V5l-3-3z" />
                      <path d="M13 2v3h3" />
                    </svg>
                  ),
                  label: "Before & after preview",
                },
              ].map((f, i) => (
                <div key={i} className="flex flex-col items-center gap-2">
                  <div className="text-[var(--color-text-dim)]">{f.icon}</div>
                  <span className="text-xs text-[var(--color-text-dim)]">
                    {f.label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {view === "processing" && batchId && (
          <ProcessingView
            batchId={batchId}
            onComplete={handleComplete}
            onSessionExpired={handleSessionExpired}
          />
        )}

        {view === "result" && (
          <ResultView jobs={jobs} batchId={batchId} onReset={handleReset} />
        )}
      </main>
    </div>
  );
}

export default App;
