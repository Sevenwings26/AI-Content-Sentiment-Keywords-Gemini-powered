# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import models, database
from app.routes import content_analyse, rag  # Import both routers

app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# Run migrations/table creation
# models.Base.metadata.create_all(bind=database.engine) # replace with alembic upgrade head

# Register Router Modules
app.include_router(content_analyse.router)
app.include_router(rag.router)





# from fastapi import FastAPI, Request, Depends
# from sqlalchemy.orm import Session
# from fastapi.templating import Jinja2Templates
# from fastapi.responses import HTMLResponse
# from app import schemas, models, database, utility
# from fastapi.middleware.cors import CORSMiddleware
# # threading module
# from starlette.concurrency import run_in_threadpool
# from pathlib import Path


# # create app 
# app = FastAPI()

# # middleware 
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_headers=["*"],
#     allow_methods=["*"],
# )

# # sync database 
# models.Base.metadata.create_all(bind=database.engine)

# # template configuration
# # templates = Jinja2Templates(directory="templates")
# BASE_DIR = Path(__file__).resolve().parent
# templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# # load database 
# def get_db():
#     db = database.SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

