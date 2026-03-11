import os
import time
import uuid
import threading


class JobStore:
    def __init__(self, cleanup_after_seconds: int = 600):
        self._jobs: dict[str, dict] = {}
        self._batches: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._cleanup_after = cleanup_after_seconds

    def create_batch(self, files: list[dict]) -> tuple[str, list[dict]]:
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        jobs = []
        with self._lock:
            job_ids = []
            for f in files:
                job_id = uuid.uuid4().hex[:12]
                job = {
                    "id": job_id,
                    "batch_id": batch_id,
                    "filename": f["filename"],
                    "status": "queued",
                    "watermark_detected": None,
                    "error": None,
                    "created_at": time.time(),
                    "completed_at": None,
                    "input_path": None,
                    "output_path": None,
                }
                self._jobs[job_id] = job
                job_ids.append(job_id)
                jobs.append(dict(job))
            self._batches[batch_id] = job_ids
        return batch_id, jobs

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_batch(self, batch_id: str) -> list[dict] | None:
        with self._lock:
            job_ids = self._batches.get(batch_id)
            if job_ids is None:
                return None
            return [dict(self._jobs[jid]) for jid in job_ids if jid in self._jobs]

    def update_job(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                job[key] = value
            if job["status"] in ("done", "error") and job["completed_at"] is None:
                job["completed_at"] = time.time()

    def cleanup(self) -> None:
        import shutil
        import tempfile
        now = time.time()
        with self._lock:
            expired = [
                jid for jid, job in self._jobs.items()
                if job["completed_at"] is not None
                and (now - job["completed_at"]) > self._cleanup_after
            ]
            for jid in expired:
                job = self._jobs.pop(jid, None)
                if job:
                    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{jid}")
                    if os.path.exists(job_dir):
                        shutil.rmtree(job_dir, ignore_errors=True)
                    bid = job.get("batch_id")
                    if bid in self._batches:
                        self._batches[bid] = [j for j in self._batches[bid] if j != jid]
                        if not self._batches[bid]:
                            del self._batches[bid]
