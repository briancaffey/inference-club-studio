import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import cuts, generations, health, projects, takes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Inference Club Studio",
    description="Audio/video processing backend with agentic AI capabilities",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — open for local dev (any origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Ensure media directory exists
media_path = Path(settings.media_dir)
media_path.mkdir(parents=True, exist_ok=True)

# Serve media files
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

# Routes
app.include_router(health.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(cuts.router, prefix="/api/v1")
app.include_router(generations.router, prefix="/api/v1")
app.include_router(takes.router, prefix="/api/v1")
