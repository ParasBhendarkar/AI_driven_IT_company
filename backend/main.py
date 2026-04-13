from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import (
    auth_router,
    github_router,
    tasks_router,
    inbox_router,
    memory_router,
    activity_router,
)
from config import settings
from database import init_db
from memory.long_term import ensure_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Ensuring Qdrant collection...")
    await ensure_collection()
    yield
    logger.info("Shutdown")


app = FastAPI(
    title="Conductor API",
    version="1.0.0",
    description="AI-driven software company backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(github_router)
app.include_router(tasks_router)
app.include_router(inbox_router)
app.include_router(memory_router)
app.include_router(activity_router)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
