from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import auth, events, projects

app = FastAPI(
    title="DevFlow API",
    version="0.1.0",
    description="Backend API for tracking project git branches and events.",
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(projects.router)


@app.get("/health", summary="Basic service health check")
def health_check() -> dict[str, str]:
    """Return service status to verify the API server is alive."""
    return {"status": "ok"}


@app.get("/health/db", summary="Database connectivity health check")
def health_db_check(db: Session = Depends(get_db)) -> dict[str, str]:
    """Test connection to the PostgreSQL database with a simple query."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unreachable: {exc}",
        ) from exc
