from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    filename: str
    status: str
    watermark_detected: bool | None = None
    preview_url: str | None = None
    original_url: str | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    batch_id: str
    jobs: list[JobResponse]


class UploadResponse(BaseModel):
    batch_id: str
    jobs: list[JobResponse]
    errors: list[dict]


class ErrorResponse(BaseModel):
    error: str
    detail: str
