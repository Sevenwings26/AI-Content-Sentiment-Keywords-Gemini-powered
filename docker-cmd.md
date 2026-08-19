docker compose up -d --build
docker compose logs -f
docker compose exec wings_retrival_ai alembic revision --autogenerate -m "add rag chat models"

docker compose exec wings_retrival_ai alembic upgrade head
