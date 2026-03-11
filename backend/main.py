import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import health

app = FastAPI(title="Watermark Remover API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
