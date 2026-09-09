# app/main.py
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from app.routes import auth, chat, documents, governance, jobs, audit, views, indexes

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise-grade Unified Cognitive RAG Platform with Multi-Source Retrieval, Dynamic RBAC, and Grounding Guardrails."
)

# Static Files Directory
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# Register API Routers first (ensures specific API paths are evaluated before view wildcards)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(governance.router)
app.include_router(jobs.router)
app.include_router(audit.router)
app.include_router(indexes.router)

# Register UI View Routers last
app.include_router(views.router)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER
    }
