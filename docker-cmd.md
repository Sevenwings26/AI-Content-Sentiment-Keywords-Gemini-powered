
# Generate migration script
docker compose exec wings_retrival_ai alembic revision --autogenerate -m "describe_changes"

# Apply migration
docker compose exec wings_retrival_ai alembic upgrade head


# Rebuild containers
docker compose build --no-cache
docker compose up -d --build
docker compose logs -f

# Start all services (FastAPI, Celery, Qdrant, Redis)
docker compose up -d

# View live FastAPI app logs
docker compose logs -f wings_retrival_ai

# View live Celery worker logs
docker compose logs -f wings_ingestion_worker
