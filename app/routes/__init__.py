# app/routes/__init__.py
from app.routes import auth, chat, documents, governance, jobs, audit, views

__all__ = [
    "auth",
    "chat",
    "documents",
    "governance",
    "jobs",
    "audit",
    "views"
]
