import os
import logging
import asyncio
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from datetime import datetime
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
FLY_API_TOKEN = os.getenv("FLY_API_TOKEN")
FLY_APP_NAME = "moodboard"


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

    http_status = 200

    # --- Database check ---
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        status["database"] = "connected"
    except Exception as e:
        status["database"] = f"error: {e}"
        http_status = 503

    # --- Redis check with lazy reconnect + backoff ---
    try:
        redis = request.app.state.redis
        try:
            await redis.ping()
            status["redis"] = "connected"
        except Exception:
            logger.warning("Redis connection lost — attempting reconnect...")
            redis = await reconnect_redis_with_backoff()
            request.app.state.redis = redis
            status["redis"] = "reinitialized"
    except Exception as e:
        status["redis"] = f"error: {e}"
        http_status = 503

    # --- Worker heartbeat ---
    try:
        heartbeat = await request.app.state.redis.get("arq:heartbeat")
        if heartbeat:
            last_heartbeat = datetime.fromtimestamp(float(heartbeat))
            status["worker"] = f"running (last heartbeat {last_heartbeat.isoformat()})"
        else:
            status["worker"] = "not reporting"
            http_status = 503
            await restart_worker_via_api()

    except Exception as e:
        status["worker"] = f"error: {e}"
        http_status = 503
        await restart_worker_via_api()

    return JSONResponse(content=status, status_code=http_status)


async def reconnect_redis_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """
    Attempt to reconnect to Redis using exponential backoff.
    Returns the new Redis pool or raises after all retries fail.
    """
    for attempt in range(max_retries):
        try:
            redis = await create_pool(RedisSettings.from_dsn(os.getenv("REDIS_URL")))
            await redis.ping()
            logger.info(f"Redis reconnected on attempt {attempt + 1}")
            return redis
        except Exception as e:
            wait_time = base_delay * (2**attempt)
            logger.warning(f"Redis reconnect attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(wait_time)
    raise RuntimeError("Failed to reconnect to Redis after multiple attempts")


async def restart_worker_via_api():
    """
    Restart the Fly.io worker machine using the Machines HTTP API.
    Assumes you labeled your worker machines with `process=worker`.
    """
    try:
        async with httpx.AsyncClient() as client:
            # 1. Get machine list
            logger.warning(f"🚨 Fly api token is:  {FLY_API_TOKEN}...")
            res = await client.get(
                f"https://api.machines.dev/v1/apps/{FLY_APP_NAME}/machines",
                headers={"Authorization": f"Bearer {FLY_API_TOKEN}"},
            )
            res.raise_for_status()
            machines = res.json()

            # Fly returns a list of machine definitions; filter for ones running the 'worker' process
            worker_machines = [
                m for m in machines
                if "worker" in (m.get("processes") or [])
            ]

            if not worker_machines:
                logger.error("❌ No worker machine found to restart")
                return False

            # Select first worker machine
            worker = worker_machines[0]
            worker_id = worker["id"]
            logger.info(f"🔄 Restarting worker {worker_id}...")

            res = httpx.post(
                f"https://api.machines.dev/v1/apps/{FLY_APP_NAME}/machines/{worker_id}/restart",
                headers={"Authorization": f"Bearer {FLY_API_TOKEN}"},
            )
            res.raise_for_status()
            logger.info("✅ Worker restarted successfully")
            return True


    except Exception as e:
        logger.error(f"⚠️ Failed to restart worker via API: {e}", exc_info=True)
