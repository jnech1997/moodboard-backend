import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.db.base import Base
from app.db.session import engine
from app.api.routes import boards, board_items, search, system

# Load logging config if present
if os.path.exists("logging.conf"):
    logging.config.fileConfig("logging.conf", disable_existing_loggers=False)  # type: ignore
logger = logging.getLogger("root")

# Detect environment (default to production)
ENV = os.getenv("APP_ENV", "production").lower()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")

    yield  # App runs here

    # Shutdown logic (if needed)
    logger.info("Shutting down...")


# Create FastAPI app with lifespan
app = FastAPI(
    title="MoodBoard API",
    version="0.4",
    lifespan=lifespan,
)

# Dev-only CORS settings
if ENV == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS allowed for development environment")
else:
    logger.info("Running in production environment - CORS restricted")

# Static files
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# API routes
app.include_router(boards.router)
app.include_router(board_items.router)
app.include_router(search.router)
app.include_router(system.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
