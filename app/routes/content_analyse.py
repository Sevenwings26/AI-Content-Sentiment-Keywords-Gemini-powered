from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from app import schemas, models, database, utility

from starlette.concurrency import run_in_threadpool
from pathlib import Path

# base dir 
BASE_DIR = Path(__file__).resolve().parent.parent
# template 
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

#
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# get
@router.get('/content-generator', response_class=HTMLResponse)
def read_root(request: Request):
    # render
    return templates.TemplateResponse('content_generator.html', {"request": request})

# post 
@router.post("/generate/")
async def generate_content(payload: schemas.GeneratePayload, db: Session = Depends(get_db)):
    generated_text = await run_in_threadpool(utility.generate_context, db, payload.topic)
    return {'generated_text':generated_text}


@router.post("/analyze/")
async def analyze_content(payload: schemas.AnalyzePayload, db: Session = Depends(get_db)):
    readability, sentiment = await run_in_threadpool(utility.analyze_content, db, payload.content)
    return {'readability': readability, "sentiment": sentiment}

# for SEOs
@router.post("/keywords/")
async def extract_keywords(payload: schemas.KeywordPayload, db: Session = Depends(get_db)):
    keywords = await run_in_threadpool(utility.get_keywords, db, payload.content)
    # print(keywords)
    return {"keywords":keywords}


