import BeforeAfterSlider from "./BeforeAfterSlider";
import { previewUrl, downloadUrl, downloadAllUrl } from "../api";

export default function ResultView({ jobs, batchId, onReset }) {
  const doneJobs = jobs.filter((j) => j.status === "done");
  const errorJobs = jobs.filter((j) => j.status === "error");

  return (
    <div className="mt-10">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Results ({doneJobs.length} of {jobs.length} processed)
        </h3>
        <div className="flex gap-2">
          {doneJobs.length > 1 && (
            <a
              href={downloadAllUrl(batchId)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500"
            >
              Download All
            </a>
          )}
          <button
            onClick={onReset}
            className="rounded-lg bg-gray-800 px-4 py-2 text-sm font-medium hover:bg-gray-700"
          >
            Remove more
          </button>
        </div>
      </div>

      {errorJobs.length > 0 && (
        <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
          {errorJobs.map((job) => (
            <p key={job.id}>
              {job.filename}: {job.error || "Processing failed"}
            </p>
          ))}
        </div>
      )}

      <div className="mt-6 space-y-6">
        {doneJobs.map((job) => (
          <div key={job.id} className="rounded-xl bg-gray-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-medium">{job.filename}</p>
                {job.watermark_detected === false && (
                  <p className="text-xs text-yellow-400">
                    No watermark detected — file returned as-is
                  </p>
                )}
              </div>
              <a
                href={downloadUrl(job.id)}
                className="rounded-lg bg-gray-700 px-3 py-1.5 text-sm hover:bg-gray-600"
              >
                Download
              </a>
            </div>
            {job.watermark_detected !== false && (
              <BeforeAfterSlider
                beforeSrc={previewUrl(job.id, "original")}
                afterSrc={previewUrl(job.id)}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
