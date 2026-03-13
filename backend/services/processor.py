import os
import asyncio
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

from services.job_store import JobStore
from services.image_processor import ImageProcessor
from services.pdf_processor import PdfProcessor

_executor = ThreadPoolExecutor(max_workers=2)
_image_processor = ImageProcessor()
_pdf_processor = PdfProcessor()
_job_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}


def _get_job_lock(job_id: str) -> threading.Lock:
    with _locks_lock:
        if job_id not in _job_locks:
            _job_locks[job_id] = threading.Lock()
        return _job_locks[job_id]


def _process_job(store: JobStore, job_id: str) -> None:
    """Synchronous processing function to run in thread pool."""
    job = store.get_job(job_id)
    if job is None:
        return

    lock = _get_job_lock(job_id)
    if not lock.acquire(blocking=False):
        return  # Another thread is already processing this job

    try:
        # Re-read job under lock to avoid race conditions
        job = store.get_job(job_id)
        if job is None or job["status"] != "queued":
            return

        store.update_job(job_id, status="processing")

        input_path = job["input_path"]
        ext = os.path.splitext(job["filename"])[1].lower()
        output_dir = os.path.join(
            tempfile.gettempdir(), f"watermark-{job_id}"
        )
        os.makedirs(output_dir, exist_ok=True)

        if ext in IMAGE_EXTENSIONS:
            result = _image_processor.process(input_path, output_dir)
        elif ext in PDF_EXTENSIONS:
            result = _pdf_processor.process(input_path, output_dir)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Count pages for PDF files so frontend can show navigation
        page_count = 1
        if ext in PDF_EXTENSIONS:
            try:
                import fitz
                doc = fitz.open(result["output_path"])
                page_count = len(doc)
                doc.close()
            except Exception:
                pass

        store.update_job(
            job_id,
            status="done",
            output_path=result["output_path"],
            watermark_detected=result["watermark_detected"],
            page_count=page_count,
        )

    except Exception as e:
        store.update_job(job_id, status="error", error=str(e))
    finally:
        lock.release()


async def dispatch_job(store: JobStore, job_id: str) -> None:
    """Dispatch a job to the thread pool with timeout."""
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_executor, _process_job, store, job_id),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        store.update_job(job_id, status="error", error="Processing timed out (60s limit)")
    except Exception as e:
        store.update_job(job_id, status="error", error=str(e))
