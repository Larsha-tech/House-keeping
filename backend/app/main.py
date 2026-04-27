"""HOBB FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .core.config import settings
from .core.logging import logger, setup_logging
from .core.rate_limit import limiter
from .database import Base, SessionLocal, engine
from .routes import (
    attendance,
    audit,
    auth,
    checklist,
    comments,
    locations,
    reports,
    tasks,
    upload,
    users,
)
from .schemas import HealthResponse
from .seed import seed
from .services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting %s v%s (env=%s)", settings.APP_NAME, __version__, settings.APP_ENV)

    # Make sure upload dir exists
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    # Auto-create tables (Alembic is provided but create_all makes dev workflow frictionless).
    Base.metadata.create_all(bind=engine)

    # Seed
    db = SessionLocal()
    try:
        seed(db)
    except Exception:
        logger.exception("seed failed")
    finally:
        db.close()

    # Start background scheduler
    start_scheduler()

    yield

    stop_scheduler()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Rate limit middleware
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Gzip large responses
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Trusted hosts (loose by default, tighten in production)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    # Static files - serve uploads directly when running without nginx
    uploads_dir = Path(settings.UPLOAD_DIR)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/storage/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    # --- global exception handlers ---
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        logger.warning("validation error path=%s errors=%s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    # --- routes ---
    prefix = settings.API_PREFIX
    app.include_router(auth.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(tasks.router, prefix=prefix)
    app.include_router(checklist.router, prefix=prefix)
    app.include_router(comments.router, prefix=prefix)
    app.include_router(attendance.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(upload.router, prefix=prefix)
    app.include_router(locations.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse(status="ok", version=__version__)

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "app": settings.APP_NAME,
            "version": __version__,
            "docs": "/api/docs",
        }

    return app


app = create_app()
