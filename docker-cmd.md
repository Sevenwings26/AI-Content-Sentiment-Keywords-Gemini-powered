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

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'testdb'
AND pid <> pg_backend_pid();

# Rebuild containers

docker compose build --no-cache
docker compose up -d --build

# Start all services (FastAPI, Celery, Qdrant, Redis)

docker compose up -d

# View live FastAPI app logs

docker compose logs -f wings_retrival_ai

# View live Celery worker logs

docker compose logs -f wings_ingestion_worker

docker compose exec wings_retrival_ai alembic init alembic

# Generate migration script

docker compose exec wings_retrival_ai alembic revision --autogenerate -m "describe_changes"

# Apply migration

docker compose exec wings_retrival_ai alembic upgrade head

# To execute python script

docker compose exec wings_retrival_ai python benchmarking/test_verification.py

# OR

# 1. Open an interactive shell inside the container

docker compose exec -it wings_retrival_ai /bin/bash

# 2. Inside the container shell, run:

python benchmarking/test_verification.py

# 3. Exit the container shell when done:

exit
