import os
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from contextlib import asynccontextmanager

from app.db.base import Base
from arq import create_pool
from arq.connections import RedisSettings
from app.db.session import engine, async_session
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
    app.state.redis = await create_pool(RedisSettings.from_dsn(os.getenv("REDIS_URL")))
    logger.info("Database initialized")

    yield  # App runs here

    # Shutdown logic (if needed)
    await app.state.redis.close()
    await app.state.redis.connection_pool.disconnect()
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

if ENV == "production":
    origins = [
        "https://moodboard-frontend-ten.vercel.app",  # deployed frontend
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

STATIC_FILES_DIR = "/app/static"
os.makedirs(STATIC_FILES_DIR, exist_ok=True)
# Static files
app.mount("/static", StaticFiles(directory=STATIC_FILES_DIR), name="static")

# API routes
app.include_router(boards.router)
app.include_router(board_items.router)
app.include_router(search.router)
app.include_router(system.router)


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request):
    status = {
        "api": "ok",
        "database": None,
        "redis": None,
        "worker": None,
    }

    # Check database connection
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        status["database"] = "connected"
    except Exception as e:
        status["database"] = f"error: {str(e)}"

    # Check Redis from app state
    try:
        redis = request.app.state.redis
        await redis.ping()
        status["redis"] = "connected"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"

    # Worker check…
    try:
        heartbeat = await redis.get("arq:heartbeat")
        if heartbeat:
            status["worker"] = "running"
        else:
            status["worker"] = "not reporting"
    except Exception as e:
        status["worker"] = f"error: {str(e)}"

    return status
