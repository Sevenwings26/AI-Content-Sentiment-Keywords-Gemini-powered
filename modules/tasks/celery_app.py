# modules/tasks/celery_app.py
import os
from core.config import settings

REDIS_URL = settings.REDIS_URL or os.getenv("REDIS_URL", "redis://redis:6379/0")

try:
    from celery import Celery
    celery_app = Celery(
        "enterprise_rag_tasks",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=["modules.tasks.workers.ingestion_tasks"]
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,
    )
except ImportError:
    class MockTaskResult:
        def __init__(self, task_id="mock-task-id"):
            self.id = task_id

    class MockCeleryApp:
        def __init__(self):
            self.tasks = {}
            self.conf = {}

        def task(self, *args, **kwargs):
            def decorator(fn):
                name = kwargs.get("name", fn.__name__)
                def delay(*fn_args, **fn_kwargs):
                    return MockTaskResult()
                fn.delay = delay
                self.tasks[name] = fn
                return fn
            return decorator

    celery_app = MockCeleryApp()
