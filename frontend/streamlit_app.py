import streamlit as st
import os, json, random, re, tempfile, subprocess, base64, shutil
from datetime import datetime
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
import fitz

import sys
import os

# Force add project root path
sys.path.append(r"C:\Users\Harsh\Downloads\Q_A_Chatbot_Using_Agentic_RAG_Architecture\q_a_chatbot")


# ===== Backend Imports =====
from backend.app.services.github_service import fetch_and_analyze_github
from backend.app.services.llm_service import summarize_project, fix_latex_syntax_with_llm
from backend.app.services.latex_service import generate_resume_latex
from backend.app.services.embedding_service import embed_resume_text, embed_project_summaries
from backend.app.services.qualification_service import verify_and_notify_qualification
# from backend.app.services.chatbot_service import query_rag_response 
from backend.app.services.agentic_rag_service import agentic_rag_pipeline

# ===== Setup =====
load_dotenv()
DATA_DIR = "data"
USER_DATA_PATH = os.path.join(DATA_DIR, "user_data.json")
EMBED_DIR = os.path.join(DATA_DIR, "embeddings")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EMBED_DIR, exist_ok=True)



API_KEYS = [os.getenv(f"GROQ_API_KEY_{i}") for i in range(1, 6)]

def get_random_llm():
    key = random.choice([k for k in API_KEYS if k])
    return ChatGroq(api_key=key, model="openai/gpt-oss-120b", temperature=0.7)

def load_user_data():
    if os.path.exists(USER_DATA_PATH):
        with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(USER_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== Streamlit UI =====
st.set_page_config(page_title="Agentic Resume Chatbot", layout="wide")
st.title("🤖 Agentic Resume RAG Builder + Chatbot")

if "user_data" not in st.session_state:
    st.session_state["user_data"] = load_user_data()

user_data = st.session_state["user_data"]
llm = get_random_llm()

# ==========================================================
# 🔹 SECTION SELECTOR
# ==========================================================
page = st.sidebar.radio("Select View", ["📄 Resume & Project Builder", "💬 RAG Chatbot"])

# ==========================================================
# 📄 PART 1 — Resume & GitHub Processor
# ==========================================================
if page == "📄 Resume & Project Builder":
    # ========== QUALIFICATION ==========
    st.header("🎓 Basic Qualification Information")

    qual = user_data.get("qualification", {})
    col1, col2 = st.columns(2)
    with col1:
        cgpa = st.text_input("Enter your CGPA", value=qual.get("cgpa", ""), placeholder="e.g., 9.14")
    with col2:
        skill = st.text_input("Enter your Key Skill", value=qual.get("skill", ""), placeholder="e.g., LangChain")

    user_data.setdefault("qualification", {})
    user_data["qualification"]["cgpa"] = cgpa.strip()
    user_data["qualification"]["skill"] = skill.strip()
    save_user_data(user_data)

    with st.expander("📋 Current Qualification Data", expanded=False):
        st.json(user_data["qualification"])

    # ========== RESUME UPLOAD ==========
    st.header("1️⃣ Upload and Extract Resume")

    uploaded = st.file_uploader("📄 Upload Resume (PDF)", type=["pdf"])
    if uploaded:
        save_path = os.path.join(DATA_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.success(f"✅ Uploaded {uploaded.name}")

        with st.spinner("🔍 Extracting text from resume..."):
            pdf_doc = fitz.open(save_path)
            pdf_text = "".join(page.get_text("text") for page in pdf_doc)
            pdf_doc.close()

        with st.spinner("🤖 Parsing resume using LLM..."):
            prompt = f"You are a professional resume parser. Extract key details in JSON from:\n{pdf_text}"
            resp = llm.invoke(prompt)
            text = getattr(resp, "content", str(resp))
            match = re.search(r'\{[\s\S]*\}', text)
            parsed_data = json.loads(match.group(0)) if match else {}

        # Preserve qualification safely
        qualification_data = user_data.get("qualification", {"cgpa": cgpa, "skill": skill})
        user_data = {**user_data, **parsed_data}
        user_data["qualification"] = qualification_data

        save_user_data(user_data)
        st.session_state["user_data"] = user_data
        st.success("✅ Resume extracted and saved!")

        verify_and_notify_qualification(parsed_data, cgpa, skill, llm)

        with st.expander("🧾 Extracted Data"):
            st.json(parsed_data)

        with st.spinner("📚 Generating embeddings for resume..."):
            try:
                path = embed_resume_text(parsed_data)
                st.success(f"✅ Resume embeddings stored at {path}")
            except Exception as e:
                st.error(f"❌ Failed to embed resume: {e}")

    # ========== GITHUB REPOS ==========
    st.header("2️⃣ Fetch and Summarize GitHub Projects")
    github = st.text_input("🐙 Enter GitHub Username or URL", value=user_data.get("github", ""))

    if st.button("Fetch & Process Repositories"):
        uname = github.strip().rstrip("/").split("/")[-1]
        if not uname:
            st.warning("⚠️ Please enter a valid GitHub username.")
        else:
            with st.spinner("📥 Fetching repositories..."):
                try:
                    repos = fetch_and_analyze_github(uname)
                except Exception as e:
                    st.error(f"❌ GitHub fetch failed: {e}")
                    repos = []

            if repos:
                st.success(f"✅ Retrieved {len(repos)} repositories!")
                with st.spinner("🧠 Summarizing via LLM..."):
                    summaries = []
                    for r in repos:
                        try:
                            summaries.append(summarize_project(r, user_data.get("role", "")))
                        except Exception as e:
                            st.warning(f"⚠️ Skipped one repo: {e}")
                    st.session_state["summaries"] = summaries
                    st.success(f"✅ Summarized {len(summaries)} projects!")

                with st.expander("🧩 Project Summaries"):
                    st.json(summaries)

                with st.spinner("📚 Generating project embeddings..."):
                    try:
                        path = embed_project_summaries(summaries)
                        st.success(f"✅ Project embeddings saved at {path}")
                    except Exception as e:
                        st.error(f"❌ Failed to embed project summaries: {e}")

# ==========================================================
# 💬 PART 2 — CHATBOT INTERFACE
# ==========================================================
elif page == "💬 RAG Chatbot":


    st.header("💬 Chat with Your Resume and Projects")

    user_query = st.chat_input("Ask about your resume or projects...")

    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = agentic_rag_pipeline(user_query)
                st.markdown(answer)
