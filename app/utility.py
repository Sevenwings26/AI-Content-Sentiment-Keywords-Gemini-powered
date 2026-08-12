import os
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app import crud
import google.generativeai as genai
import threading

# environment 
load_dotenv()

# Gemini API configuration
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize Gemini model
model = genai.GenerativeModel("gemini-2.5-flash")

# Semaphore to control threading (up to 5 threads at once)
semaphore = threading.Semaphore(5)

# Generate content using Gemini model
def generate_context(db: Session, topic: str):
    with semaphore:
        search_term = crud.get_search_term(db, topic)
        if not search_term:
            search_term = crud.create_search_term(db, topic)

        prompt = f"You are a helpful assistant. Write a detailed article about {topic}."
        response = model.generate_content(prompt)
        generate_text = response.text.strip()

        # Store generated text in the database
        crud.create_search_content(db, generate_text, search_term.id)
        return generate_text

# Analyze content: readability + sentiment
def analyze_content(db: Session, content: str):
    with semaphore:
        search_term = crud.get_search_term(db, content)
        if not search_term:
            search_term = crud.create_search_term(db, content)

        readability = get_readability_score(content)
        sentiment = get_sentiment_analysis(content)

        crud.create_sentiment_analysis(db, readability, sentiment, search_term.id)

        return readability, sentiment

# Dummy readability logic (replace with real logic if needed)
def get_readability_score(content: str) -> str:
    return "Readability Score: Good"

# Perform sentiment analysis
def get_sentiment_analysis(content: str) -> str:
    prompt = (
        f"Analyze the sentiment of the following text:\n\n{content}\n\n"
        "Is the sentiment positive, neutral, or negative?"
    )
    response = model.generate_content(prompt)
    return response.text.strip()


# keywword extractor
def get_keywords(db: Session, content: str) -> str:
    with semaphore:
        search_term = crud.get_search_term(db, content)
        if not search_term:
            search_term = crud.create_search_term(db, content)

        prompt = (
            f"You are a marketing strategist and SEO expert. Extract the most relevant and high-ranking keywords for SEO campaigns from the following content:\n\n{content}\n\n"
            "Return them as a comma-separated list."
        )
        response = model.generate_content(prompt)
        keywords_text = response.text.strip()

        crud.create_keywords(db, keywords_text, search_term.id)

        return keywords_text


# Perform content summary
def get_content_summary(content: str) -> str:
    prompt = (
        f"Fetch keywords of the following text:\n\n{content}\n\n, for SEO optimaimizations"
    )
    response = model.generate_context(prompt)
    return response











# import os
# import crud, models

# from sqlalchemy.orm import Session
# from dotenv import load_dotenv
# import threading
# # from concurrent.futures import ThreadPoolExecutor  

# from openai import OpenAI


# load_dotenv()

# # # using OpenAI 
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# # client = OpenAI(
# #     api_key=os.getenv("GEMINI_API_KEY"),
# #     base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
# # )


# # Semaphore to control threading
# semaphore = threading.Semaphore(5) # allows 5 threads at a time. 

# # Generate context using chat model
# def generate_context(db: Session, topic: str):
#     with semaphore:
#         search_term = crud.get_search_term(db, topic)
#         if not search_term:
#             search_term = crud.create_search_term(db, topic)

#         """OPEN-AI"""    
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",  # correct model for chat
#             # model="gemini-2.5-flash",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": f"Write a detailed article about {topic}"},
#             ]
#         )
#         # Extract generated context from the response 
#         generate_text = response.choices[0].message.content.strip()

#         # store generated text in database 
#         crud.create_search_content(db, generate_text, search_term.id)
#         return generate_text



# # Analyze content: readability + sentiment
# def analyze_content(db: Session, content: str):
#     with semaphore:
#         search_term = crud.get_search_term(db, content)
#         if not search_term:
#             search_term = crud.create_search_term(db, content)

#         readability = get_readability_score(content)
#         sentiment = get_sentiment_analysis(content)
#         crud.create_sentiment_analysis(db, readability, sentiment, search_term.id)
#         return readability, sentiment


# # Dummy readability logic (you can integrate actual NLP here)
# def get_readability_score(content: str) -> str:
#     return "Readability Score: Good"

# # Use chat model for sentiment analysis 
# def get_sentiment_analysis(content: str) -> str:
#     response = client.chat.completions.create(
#         # model="gpt-3.5-turbo",
#         model="gemini-2.5-flash",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant."},
#             {"role": "user", "content": f"Analyze the sentiment of the following text:\n\n{content}\n\nIs the sentiment positive, neutral, or negative?"},
#         ],
#         max_tokens=10
#     )
#     return response.choices[0].message.content.strip()
