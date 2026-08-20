# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import models, database
from app.routes import content_analyse, rag, enterprise_rag

app = FastAPI(
    title="Enterprise Multi-Tenant AI & RAG Platform",
    version="2.0.0",
    description="Enterprise-grade RAG pipeline with Multi-Tenancy, RBAC, Payload Isolation, and Re-ranking."
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# Run table creation for all registered models
# models.Base.metadata.create_all(bind=database.engine)

# Register Router Modules
app.include_router(content_analyse.router)
app.include_router(rag.router)
app.include_router(enterprise_rag.router)

