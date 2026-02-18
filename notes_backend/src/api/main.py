from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import init_engine
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


@app.on_event("startup")
async def _startup() -> None:
    """Initialize shared resources (DB engine)."""
    init_engine()


@app.get("/", tags=["health"], summary="Health check", description="Simple health endpoint.", operation_id="health")
def health_check():
    """Return service health status."""
    return {"message": "Healthy"}


app.include_router(notes_router)
