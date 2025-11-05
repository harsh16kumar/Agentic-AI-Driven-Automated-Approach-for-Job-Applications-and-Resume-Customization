import os
import json
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

BASE_PATH = "data/embeddings"
RESUME_PATH = os.path.join(BASE_PATH, "resume")
PROJECT_PATH = os.path.join(BASE_PATH, "projects")
os.makedirs(RESUME_PATH, exist_ok=True)
os.makedirs(PROJECT_PATH, exist_ok=True)

def embed_resume_text(resume_data: dict):
    resume_text = json.dumps(resume_data, ensure_ascii=False, indent=2)
    index = FAISS.from_texts([resume_text], embedding_model)
    path = os.path.join(RESUME_PATH, "resume_index.faiss")
    index.save_local(path)
    return path

def embed_project_summaries(projects: list):
    texts = [
        f"Project: {p.get('title', '')}\nTech: {', '.join(p.get('technologies', []))}\n"
        f"Details: {'; '.join(p.get('features', []))}"
        for p in projects
    ]
    index = FAISS.from_texts(texts, embedding_model)
    path = os.path.join(PROJECT_PATH, "projects_index.faiss")
    index.save_local(path)
    return path
