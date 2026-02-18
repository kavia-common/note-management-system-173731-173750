import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.db import get_database_url, init_engine
from src.api.routes_notes import router as notes_router

openapi_tags = [
    {"name": "health", "description": "Service health and diagnostics."},
    {"name": "notes", "description": "CRUD, search and flags (pinned/favorite) for notes."},
]

app = FastAPI(
    title="Notes Backend API",
    description="REST API for a note management app (no auth). Provides CRUD, search, tag filtering, pin/favorite.",
    version="1.0.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend may run on a separate host/port in dev.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Convert unexpected exceptions to JSON for easier frontend/integration debugging.

    In production, we do not expose stack traces by default.
    Enable debug output by setting API_DEBUG=true.
    """
    debug = (os.getenv("API_DEBUG") or "").strip().lower() in {"1", "true", "yes", "on"}
    payload = {"detail": "Internal Server Error"}
    if debug:
        payload["exception"] = repr(exc)
        payload["traceback"] = traceback.format_exc()
    return JSONResponse(status_code=500, content=payload)


@app.on_event("startup")
async def _startup() -> None:
    """Initialize shared resources (DB engine)."""
    init_engine()


@app.get("/", tags=["health"], summary="Health check", description="Simple health endpoint.", operation_id="health")
def health_check():
    """Return service health status."""
    return {"message": "Healthy"}


@app.get(
    "/health/db",
    tags=["health"],
    summary="DB health check",
    description=(
        "Attempts to initialize the DB engine and returns resolved connection URL (redacted) plus status. "
        "Useful for diagnosing DATABASE_URL/POSTGRES_URL misconfiguration."
    ),
    operation_id="healthDb",
)
async def health_db():
    """Check that the database connection string is configured and that an engine can be created."""
    # This will raise a RuntimeError if env vars are missing; our exception handler will convert it to JSON.
    url = get_database_url()

    # Redact password if present: postgresql+asyncpg://user:pass@host/db
    redacted = url
    try:
        scheme, rest = url.split("://", 1)
        if "@" in rest and ":" in rest.split("@", 1)[0]:
            userinfo, hostinfo = rest.split("@", 1)
            user, _pwd = userinfo.split(":", 1)
            redacted = f"{scheme}://{user}:***@{hostinfo}"
    except Exception:
        # If parsing fails, just avoid leaking by returning generic info.
        redacted = "<redacted>"

    # Ensure engine init does not throw (connectivity errors show up as JSON with API_DEBUG=true).
    init_engine()
    return {"ok": True, "databaseUrl": redacted}


app.include_router(notes_router)
