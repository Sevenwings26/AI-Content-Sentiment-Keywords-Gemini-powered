from sqlalchemy.orm import Session
from app import models
import hashlib

# term hashed 
def hash_term(term: str) -> str:
    return hashlib.sha256(term.encode('utf-8')).hexdigest()


# Create a new SearchTerm entry in the database - topic
def create_search_term(db: Session, term: str):
    term_hashed = hash_term(term)
    db_search_term = models.SearchTerm(term=term, term_hash=term_hashed)
    db.add(db_search_term)
    db.commit()
    db.refresh(db_search_term)
    return db_search_term


# Retrieve an existing SearchTerm by its term (string match via hash)
def get_search_term(db: Session, term: str):
    term_hashed = hash_term(term)
    return db.query(models.SearchTerm).filter(models.SearchTerm.term_hash == term_hashed).first()


# Create a new GeneratedContent entry tied to a search term
def create_search_content(db: Session, content: str, search_term_id: int):
    db_generated_content = models.GeneratedContent(content=content, search_term_id=search_term_id)
    db.add(db_generated_content)
    db.commit()
    db.refresh(db_generated_content)
    return db_generated_content


# Create a new SentimentAnalysis entry tied to a search term
def create_sentiment_analysis(db: Session, readability: str, sentiment: str, search_term_id: int):
    db_sentiment_analysis = models.SentimentAnalysis(
        readability=readability,
        sentiment=sentiment,
        search_term_id=search_term_id
    )
    db.add(db_sentiment_analysis)
    db.commit()
    db.refresh(db_sentiment_analysis)
    return db_sentiment_analysis


# Create a new GeneratedKeywords entry linked to a search term
def create_keywords(db: Session, content: str, search_term_id: int):
    db_keywords = models.GeneratedKeywords(content=content, search_term_id=search_term_id)
    db.add(db_keywords)
    db.commit()
    db.refresh(db_keywords)
    return db_keywords

