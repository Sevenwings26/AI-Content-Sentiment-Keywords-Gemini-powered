from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app import schemas, models, database, utility
from fastapi.middleware.cors import CORSMiddleware
# threading module
from starlette.concurrency import run_in_threadpool
from pathlib import Path


# create app 
app = FastAPI()

# middleware 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# sync database 
models.Base.metadata.create_all(bind=database.engine)

# template configuration
# templates = Jinja2Templates(directory="templates")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# load database 
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# routes
# get
@app.get('/content-generator', response_class=HTMLResponse)
def read_root(request: Request):
    # render
    return templates.TemplateResponse('content_generator.html', {"request": request})

# post 
@app.post("/generate/")
async def generate_content(payload: schemas.GeneratePayload, db: Session = Depends(get_db)):
    generated_text = await run_in_threadpool(utility.generate_context, db, payload.topic)
    return {'generated_text':generated_text}


@app.post("/analyze/")
async def analyze_content(payload: schemas.AnalyzePayload, db: Session = Depends(get_db)):
    readability, sentiment = await run_in_threadpool(utility.analyze_content, db, payload.content)
    return {'readability': readability, "sentiment": sentiment}

# for SEOs
@app.post("/keywords/")
async def analyze_content(payload: schemas.KeywordPayload, db: Session = Depends(get_db)):
    keywords = await run_in_threadpool(utility.get_keywords, db, payload.content)
    # print(keywords)
    return {"keywords":keywords}


