from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey 
from sqlalchemy.orm import relationship
import hashlib
from app.database import Base

# # Table to store each unique search/topic term entered by the user.
# class SearchTerm(Base):
#     __tablename__ = "search_terms"

#     id = Column(Integer, primary_key=True, index=True)  # Unique ID for each search term
#     term = Column(String(2000), index=True)  # PostgreSQL’s B-tree index limit is ~2700 bytes per row... The actual search/topic term
#     # Relationships to link this term with other table. -  
#     generated_content = relationship("GeneratedContent", back_populates="search_term")
#     sentiment_analysis = relationship("SentimentAnalysis", back_populates="search_term")
#     generated_keywords = relationship("GeneratedKeywords", back_populates="search_term")


class SearchTerm(Base):
    __tablename__ = "search_terms"

    id = Column(Integer, primary_key=True, index=True)
    term = Column(Text)  # Long string NOT indexed
    term_hash = Column(String(64), index=True)  # Safe hashed value

    generated_content = relationship("GeneratedContent", back_populates="search_term")
    sentiment_analysis = relationship("SentimentAnalysis", back_populates="search_term")
    generated_keywords = relationship("GeneratedKeywords", back_populates="search_term")


# Table to store AI-generated content for a given search term.
class GeneratedContent(Base):
    __tablename__ = "generated_content"

    id = Column(Integer, primary_key=True, index=True)  # Unique ID for each content entry
    content = Column(Text)  # The generated text/content itself
    search_term_id = Column(Integer, ForeignKey('search_terms.id'))  # Link to the related search term

    # Establish reverse relationship to SearchTerm
    search_term = relationship("SearchTerm", back_populates="generated_content")


# Table to store analysis results (readability and sentiment) for a given search term.
class SentimentAnalysis(Base):
    __tablename__ = "sentiment_analysis"

    id = Column(Integer, primary_key=True, index=True)  # Unique ID for the analysis record
    readability = Column(String)  # e.g., "Easy", "Intermediate"
    sentiment = Column(String)  # e.g., "Positive", "Negative", "Neutral"
    search_term_id = Column(Integer, ForeignKey('search_terms.id'))  # Link to related search term
    # Reverse link to SearchTerm
    search_term = relationship("SearchTerm", back_populates="sentiment_analysis")


# Table to store the keywords extracted from the generated content.
class GeneratedKeywords(Base):
    __tablename__ = "generated_keywords"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)  # The keywords as a string or JSON
    search_term_id = Column(Integer, ForeignKey('search_terms.id'))  # Link to related search term
    # Reverse link to SearchTerm
    search_term = relationship("SearchTerm", back_populates="generated_keywords")

