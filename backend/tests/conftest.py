import pytest
from fastapi.testclient import TestClient

from main import app
from services.job_store import JobStore
from services.rate_limiter import RateLimiter


@pytest.fixture
def client():
    app.state.job_store = JobStore()
    app.state.upload_limiter = RateLimiter(max_requests=100, window_seconds=60)
    app.state.poll_limiter = RateLimiter(max_requests=100, window_seconds=60)
    return TestClient(app)
