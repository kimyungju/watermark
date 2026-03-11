import { useState, useEffect, useCallback } from "react";
import { healthCheck, uploadFiles } from "./api";
import UploadZone from "./components/UploadZone";
import ProcessingView from "./components/ProcessingView";
import ResultView from "./components/ResultView";

function App() {
  const [view, setView] = useState("upload"); // upload | processing | result
  const [batchId, setBatchId] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [uploadError, setUploadError] = useState(null);
  const [serverErrors, setServerErrors] = useState([]);
  const [uploading, setUploading] = useState(false);

  // Wake backend on page load
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
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1
            className="cursor-pointer text-lg font-bold"
            onClick={handleReset}
          >
            WatermarkOff
          </h1>
          <nav className="flex gap-4 text-sm text-gray-400">
            <a href="#how" className="hover:text-white">
              How it works
            </a>
            <a href="#faq" className="hover:text-white">
              FAQ
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-16">
        {view === "upload" && (
          <div className="text-center">
            <h2 className="text-3xl font-bold">Remove Watermarks Instantly</h2>
            <p className="mt-2 text-gray-400">
              Images & PDFs — free, no signup
            </p>
            <UploadZone onUpload={handleUpload} disabled={uploading} />
            {uploading && (
              <p className="mt-4 text-sm text-gray-400">Uploading...</p>
            )}
            {uploadError && (
              <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
                {uploadError}
              </div>
            )}
            {serverErrors.length > 0 && (
              <div className="mt-4 rounded-lg bg-yellow-900/30 p-3 text-sm text-yellow-300">
                {serverErrors.map((e, i) => (
                  <p key={i}>
                    {e.filename}: {e.error}
                  </p>
                ))}
              </div>
            )}
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
