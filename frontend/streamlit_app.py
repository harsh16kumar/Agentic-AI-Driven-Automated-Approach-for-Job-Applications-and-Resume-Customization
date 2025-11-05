import streamlit as st
import os
import random
import sys
import json
from typing import Dict, List
# from streamlit_modal import Modal
from datetime import datetime
import subprocess
import tempfile
import base64
import shutil
from dotenv import load_dotenv
from langchain_groq import ChatGroq 
import fitz
import re
import os, sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# from backend.app.services.github_service import load_local_projects
from project_refine_modal import refine_project
from backend.app.services.github_service import fetch_and_analyze_github
from backend.app.services.llm_service import summarize_project
# from backend.app.services.llm_service import refine_text
from backend.app.services.latex_service import generate_resume_latex
from backend.app.services.llm_service import fix_latex_syntax_with_llm



# ----------------------------------
# PATH CONFIG
# ----------------------------------
DATA_DIR = r"C:\Users\Harsh\Downloads\resume-agent\resume-agent-builder\data"
USER_DATA_PATH = os.path.join(DATA_DIR, "user_data.json")
GITHUB_REPO_PATH = os.path.join(DATA_DIR, "github_repos")


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GITHUB_REPO_PATH, exist_ok=True)

# Add backend imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv()

API_KEYS = [
    os.getenv("GROQ_API_KEY_1"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
    os.getenv("GROQ_API_KEY_4"),
    os.getenv("GROQ_API_KEY_5"),
]

def get_random_llm():
    api_key = random.choice(API_KEYS)  # randomly pick a key
    
    # Initialize the LLM client with the selected key
    llm = ChatGroq(
        api_key= api_key,
        model="openai/gpt-oss-120b",
        temperature=0.7
    )
    return llm

# ----------------------------------
# HELPER FUNCTIONS
# ----------------------------------
def load_user_data() -> Dict:
    if os.path.exists(USER_DATA_PATH):
        try:
            with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_user_data(data: Dict):
    """Auto-save user data to centralized JSON."""
    with open(USER_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_projects(projects: List[Dict]):
    """Store analyzed repos into /data/github_repos."""
    for p in projects:
        repo_name = p.get("repository") or p.get("repo") or "unknown_repo"
        safe_name = "".join(c for c in repo_name if c.isalnum() or c in "-_")
        path = os.path.join(GITHUB_REPO_PATH, f"{safe_name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)


def load_local_projects() -> List[Dict]:
    """Load locally stored repos (if any)."""
    projects = []
    for f in os.listdir(GITHUB_REPO_PATH):
        if f.endswith(".json"):
            try:
                with open(os.path.join(GITHUB_REPO_PATH, f), "r", encoding="utf-8") as file:
                    projects.append(json.load(file))
            except Exception:
                pass
    return projects


def update_user_data(key: str, value):
    """Reactive auto-save for every field."""
    st.session_state["user_data"][key] = value
    save_user_data(st.session_state["user_data"])

def update_from_resume(parsed_data: dict):
    """Replace all user_data in session and file with parsed resume data."""
    st.session_state["user_data"] = parsed_data
    save_user_data(parsed_data)
    st.success("✅ Resume data replaced successfully!")


def save_user_projects_to_disk(selected_projects):
    """
    Appends only newly selected projects into existing user_data.json.
    Preserves other user info (name, email, etc.).
    Avoids duplicates by 'title'.
    """
    path = os.path.join(DATA_DIR, "user_data.json")

    # Step 1 — Load existing full user data (profile + maybe old projects)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                user_data = json.load(f)
            except Exception:
                user_data = {}
    else:
        user_data = {}

    # Step 2 — Extract existing project list
    existing_projects = user_data.get("projects", [])

    # Step 3 — Make a set of titles to detect duplicates
    existing_titles = {p.get("title", "").strip().lower() for p in existing_projects}

    # Step 4 — Filter new ones (avoid duplicates)
    new_projects = [
        p for p in selected_projects
        if p.get("title", "").strip().lower() not in existing_titles
    ]

    # Step 5 — Append new projects
    user_data["projects"] = existing_projects + new_projects

    # Step 6 — Save back to disk
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
        st.toast(f"💾 Added {len(new_projects)} new projects!", icon="✅")
    except Exception as e:
        st.error(f"❌ Failed to save projects: {e}")



# Helper: load previously saved user data (if any)

def load_user_projects_from_disk():
    path = os.path.join(DATA_DIR, "user_data.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def load_existing_summaries():
    """
    Load all pre-summarized project JSON files from the project_details folder.
    Returns a list of dicts, one per project.
    """
    summaries = []

    if not os.path.exists(PROJECT_DETAILS_DIR):
        st.warning(f"⚠️ Project details folder not found: {PROJECT_DETAILS_DIR}")
        return summaries

    files = sorted([f for f in os.listdir(PROJECT_DETAILS_DIR) if f.endswith(".json")])

    if not files:
        st.info("ℹ️ No pre-summarized project files found yet.")
        return summaries

    for fname in files:
        full_path = os.path.join(PROJECT_DETAILS_DIR, fname)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # Validate structure
                if isinstance(data, dict) and "title" in data:
                    summaries.append(data)
                else:
                    st.warning(f"⚠️ Skipping invalid or empty JSON: {fname}")
        except Exception as e:
            st.error(f"❌ Failed to load {fname}: {e}")

    if summaries:
        st.success(f"✅ Loaded {len(summaries)} summarized projects from disk.")
    else:
        st.warning("⚠️ No valid summaries found in the project_details folder.")

    return summaries


if "user_data" not in st.session_state:
    st.session_state["user_data"] = load_user_data()

# ----------------------------------
# STREAMLIT FRONTEND
# ----------------------------------
st.set_page_config(page_title="Agentic Resume Builder", layout="centered")
st.title("Agentic Resume Builder — Streamlit Frontend")

# ---- Target Role (persistent across refresh) ----
role_value = st.text_input(
    "🎯 Target role (used to tailor project bullets)",
    value=st.session_state.get("user_data", {}).get("role", ""),
    key="target_role_input"
)

target_role = st.session_state["user_data"].get("role", "")

# Persist to session + disk only if changed
if role_value != st.session_state["user_data"].get("role", ""):
    update_user_data("role", role_value)


st.header("1) Choose: Upload resume or Create from scratch")

mode = st.radio("Mode", ["Upload PDF resume", "Create from scratch"])

# Initialize
if "user_data" not in st.session_state:
    st.session_state["user_data"] = load_user_data()
if "projects" not in st.session_state:
    st.session_state["projects"] = []
if "modal_open" not in st.session_state:
    st.session_state["modal_open"] = False

user_data = st.session_state["user_data"]
llm = get_random_llm()
# ----------------------------------
# Upload Mode (Enhanced for multiple entries)
# ----------------------------------

if mode == "Upload PDF resume":
    uploaded = st.file_uploader("📄 Upload your resume (PDF)", type=["pdf"])
    if uploaded:
        save_path = os.path.join(DATA_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())

        st.success(f"✅ Saved file to {save_path}")

        # Step 1: Extract text from PDF
        with st.spinner("🔍 Extracting text from resume..."):
            import fitz  # PyMuPDF
            pdf_doc = fitz.open(save_path)
            pdf_text = ""
            for page in pdf_doc:
                pdf_text += page.get_text("text")
            pdf_doc.close()

        # Step 2: Use LLM to extract structured fields
        with st.spinner("🤖 Analyzing resume and extracting structured data..."):
            extract_prompt = f"""
            You are an advanced AI resume parser.
            Extract all key information from the following resume text.
            Always return lists even if only one entry is found.

            Resume Text:
            {pdf_text}

            Return valid JSON in the following structure:
            {{
              "name": "",
              "phone": "",
              "email": "",
              "linkedin": "",
              "github": "",
              "education": [
                {{
                  "institution": "",
                  "period": "",
                  "degree": "",
                  "cgpa": "",
                  "location": ""
                }}
              ],
              "languages": [],
              "tools": [],
              "coursework": [],
              "experience": [
                {{
                  "company": "",
                  "role": "",
                  "start": "",
                  "end": "",
                  "city": "",
                  "country": "",
                  "items": []
                }}
              ],
              "achievements": [
                {{
                  "title": "",
                  "link": "",
                  "category": "",
                  "items": []
                }}
              ],
              "projects": [
                {{
                  "title": "",
                  "technologies": [],
                  "date": "",
                  "features": []
                }}
              ]
            }}
            """

            try:
                resp = llm.invoke(extract_prompt)

                if hasattr(resp, "content"):
                    response_text = resp.content
                elif isinstance(resp, str):
                    response_text = resp
                else:
                    response_text = str(resp)

                # --- Extract JSON block robustly ---
                match = re.search(r'\{[\s\S]*\}', response_text)
                if match:
                    cleaned_json = match.group(0)
                else:
                    cleaned_json = response_text.strip()

                parsed_data = json.loads(cleaned_json)

                # --- Normalize lists ---
                for key in ["education", "experience", "projects", "achievements"]:
                    if isinstance(parsed_data.get(key), dict):
                        parsed_data[key] = [parsed_data[key]]
                    elif key not in parsed_data:
                        parsed_data[key] = []

                update_from_resume(parsed_data)

                st.success("✅ Resume data extracted and saved successfully!")
                st.info("Now switch to *Create PDF Mode* to see all fields auto-filled!")

                with st.expander("🧾 Preview Extracted Data"):
                    st.json(parsed_data)

            except json.JSONDecodeError:
                st.error("❌ The AI response was not valid JSON. Try re-uploading or check resume formatting.")
                st.text(response_text)
            except Exception as e:
                st.error(f"❌ Failed to extract resume fields: {e}")




# ----------------------------------
# Create from Scratch Mode
# ----------------------------------
if mode == "Create from scratch" or st.button("Fill manual details"):

    st.subheader("Basic Information (auto-saves as you type)")
    name = st.text_input("Full name", value=user_data.get("name", ""))
    if name != user_data.get("name", ""): update_user_data("name", name)

    phone = st.text_input("Phone", value=user_data.get("phone", ""))
    if phone != user_data.get("phone", ""): update_user_data("phone", phone)

    email = st.text_input("Email", value=user_data.get("email", ""))
    if email != user_data.get("email", ""): update_user_data("email", email)

    linkedin = st.text_input("LinkedIn profile URL", value=user_data.get("linkedin", ""))
    if linkedin != user_data.get("linkedin", ""): update_user_data("linkedin", linkedin)

    github = st.text_input("GitHub profile URL or username", value=user_data.get("github", ""))
    if github != user_data.get("github", ""): update_user_data("github", github)

    # ---- Education ----
    st.subheader("Education (add multiple)")

    saved_edu = user_data.get("education", [])
    edu_cnt = st.number_input(
        "Number of education entries",
        min_value=1,
        max_value=5,
        value=len(saved_edu) or 1,
        key="edu_cnt"
    )

    education = []
    for i in range(int(edu_cnt)):
        prev = saved_edu[i] if i < len(saved_edu) else {}
        with st.expander(f"Education #{i+1}", expanded=(i == 0)):
            institution = st.text_input(f"Institution #{i+1}", value=prev.get("institution", ""), key=f"inst_{i}")
            period = st.text_input("Period (e.g., 2020 -- 2024)", value=prev.get("period", ""), key=f"period_{i}")
            degree = st.text_input("Degree", value=prev.get("degree", ""), key=f"degree_{i}")
            cgpa = st.text_input("CGPA", value=prev.get("cgpa", ""), key=f"cgpa_{i}")
            location = st.text_input("City, Country", value=prev.get("location", ""), key=f"loc_{i}")
            education.append({
                "institution": institution,
                "period": period,
                "degree": degree,
                "cgpa": cgpa,
                "location": location
            })

    update_user_data("education", education)

    st.subheader("Coursework (comma separated)")
    coursework_raw = st.text_input("Coursework list", value=", ".join(user_data.get("coursework", [])), key="coursework_raw")
    coursework = [c.strip() for c in coursework_raw.split(",") if c.strip()]
    update_user_data("coursework", coursework)

    st.subheader("Technical skills")
    lang_raw = st.text_input("Languages (comma separated)", value=", ".join(user_data.get("languages", [])), key="languages_raw")
    languages = [x.strip() for x in lang_raw.split(",") if x.strip()]
    tools_raw = st.text_input("Tools (comma separated)", value=", ".join(user_data.get("tools", [])), key="tools_raw")
    tools = [x.strip() for x in tools_raw.split(",") if x.strip()]
    update_user_data("languages", languages)
    update_user_data("tools", tools)

    st.subheader("Experience (optional)")
    saved_exp = user_data.get("experience", [])
    exp_cnt = st.number_input("Number of experiences", min_value=0, max_value=5, value=len(saved_exp) or 0, key="exp_cnt")

    experience = []
    for i in range(int(exp_cnt)):
        prev = saved_exp[i] if i < len(saved_exp) else {}
        with st.expander(f"Experience #{i+1}"):
            company = st.text_input("Company", value=prev.get("company", ""), key=f"comp_{i}")
            # city = st.text_input("City", value=prev.get("city", ""), key=f"ecity_{i}")
            # country = st.text_input("Country", value=prev.get("country", ""), key=f"ecountry_{i}")
            city = st.text_input("City", value=prev.get("city", ""), key=f"ecity_{i}")
            country = st.text_input("Country", value=prev.get("country", ""), key=f"ecountry_{i}")
            # start = st.text_input("Start Date", value=prev.get("start", ""), key=f"estart_{i}")
            # end = st.text_input("End Date", value=prev.get("end", ""), key=f"eend_{i}")
            start = st.text_input("Start Date", value=prev.get("start", ""), key=f"estart_{i}")
            end = st.text_input("End Date", value=prev.get("end", ""), key=f"eend_{i}")
            role = st.text_input("Role", value=prev.get("role", ""), key=f"erole_{i}")
            items = st.text_area("Bullet points (one per line)", value="\n".join(prev.get("items", [])), key=f"eitems_{i}")
            experience.append({
                "company": company,
                "role": role,
                "start": start,
                "end": end,
                "city": city,
                "country": country,
                "items": [l.strip() for l in items.splitlines() if l.strip()]
            })
    update_user_data("experience", experience)


    st.subheader("Achievements (optional)")
    saved_ach = user_data.get("achievements", [])
    ach_cnt = st.number_input("Number of achievements entries", min_value=0, max_value=5, value=len(saved_ach) or 0, key="ach_cnt")

    achievements = []
    for i in range(int(ach_cnt)):
        prev = saved_ach[i] if i < len(saved_ach) else {}
        with st.expander(f"Achievement #{i+1}"):
            title = st.text_input("Title", value=prev.get("title", ""), key=f"atitle_{i}")
            link = st.text_input("Link (optional)", value=prev.get("link", ""), key=f"alink_{i}")
            category = st.text_input("Category", value=prev.get("category", ""), key=f"acat_{i}")
            items = st.text_area("Items (one per line)", value="\n".join(prev.get("items", [])), key=f"aitems_{i}")
            achievements.append({
                "title": title,
                "link": link,
                "category": category,
                "items": [l.strip() for l in items.splitlines() if l.strip()]
            })
    update_user_data("achievements", achievements)


# ----------------------------------
# Manual Project Entry Section
# ----------------------------------
st.subheader("Projects (Manual Entry)")

saved_projects = user_data.get("projects", [])
proj_cnt = st.number_input(
    "Number of projects to enter manually",
    min_value=0,
    max_value=10,
    value=len(saved_projects) or 0,
    key="proj_cnt_manual"
)

manual_projects = []
for i in range(int(proj_cnt)):
    prev = saved_projects[i] if i < len(saved_projects) else {}

    with st.expander(f"Project #{i+1}", expanded=(i == 0)):
        title = st.text_input("Project Title", value=prev.get("title", ""), key=f"mtitle_{i}")
        
        tech_raw = st.text_input("Technologies (comma separated)", 
                                 value=", ".join(prev.get("technologies", [])), 
                                 key=f"mtech_{i}")
        technologies = [t.strip() for t in tech_raw.split(",") if t.strip()]

        # Month & Year picker
        col1, col2 = st.columns(2)
        with col1:
            month = st.selectbox("Month", [m for m in range(1, 13)], key=f"mmonth_{i}")
        with col2:
            year = st.selectbox("Year", [y for y in range(datetime.now().year - 5, datetime.now().year + 2)], key=f"myear_{i}")

        formatted_date = f"{month:02d}/{year}"

        features_text = st.text_area(
            "Features (bullet points, one per line)",
            value="\n".join(prev.get("features", [])),
            key=f"mfeat_{i}"
        )
        features = [f.strip() for f in features_text.splitlines() if f.strip()]

        # Select project checkbox
        is_selected = st.checkbox(f"Select '{title}' for Resume", key=f"mselect_{i}")

        manual_projects.append({
            "title": title,
            "technologies": technologies,
            "date": formatted_date,
            "features": features,
            "selected": is_selected
        })

# ---- Save Manual Projects Button ----
# new_selected=""
new_selected = [p for p in manual_projects if p["selected"] and p["title"]]
# if st.button("✅ Save Manual Projects"):
#     # Load current user_data
#     updated = load_user_data()

#     # old projects
#     existing = updated.get("projects", [])

#     # add only selected ones
#     new_selected = [p for p in manual_projects if p["selected"] and p["title"]]

#     if new_selected:
#         updated["projects"] = existing + new_selected
#         save_user_data(updated)
#         st.session_state["user_data"] = updated
#         st.success(f"✅ Added {len(new_selected)} new projects to your resume!")
#     else:
#         st.warning("⚠️ No project selected to add.")


# ---------------------------
# GITHUB FETCH (call backend, save to disk, then display)
# ---------------------------

import json
import os
import streamlit as st
from backend.app.services.github_service import fetch_and_analyze_github

# GITHUB_DIR = os.path.join("data", "github_repos")
os.makedirs(GITHUB_REPO_PATH, exist_ok=True)

def save_projects_to_disk(projects):
    """
    Save each project dict into a separate JSON file under GITHUB_REPO_PATH.
    Filename is sanitized repo name.
    """
    for p in projects:
        # try multiple keys for repo name to be robust
        repo_name = p.get("repository") or p.get("repo") or p.get("name") or "unknown_repo"
        safe_name = "".join(c for c in repo_name if c.isalnum() or c in ("-", "_")).rstrip()
        if not safe_name:
            safe_name = "repo"
        out_path = os.path.join(GITHUB_REPO_PATH, f"{safe_name}.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.warning(f"Failed to save {repo_name} -> {e}")

def load_projects_from_disk():
    """Return list of repo dicts read from GITHUB_REPO_PATH JSON files (sorted by filename)."""
    projects = []
    if not os.path.exists(GITHUB_REPO_PATH):
        return projects
    for fname in sorted(os.listdir(GITHUB_REPO_PATH)):
        if not fname.lower().endswith(".json"):
            continue
        full = os.path.join(GITHUB_REPO_PATH, fname)
        try:
            with open(full, "r", encoding="utf-8") as f:
                projects.append(json.load(f))
        except Exception as e:
            st.warning(f"Could not read {fname}: {e}")
    return projects

def update_project_in_session(title: str, refined_features: list):
    """
    Updates only the specified project's features in st.session_state['summaries'].
    Avoids reloading all summaries from disk.
    """
    summaries = st.session_state.get("summaries", [])
    for i, proj in enumerate(summaries):
        if proj.get("title") == title:
            summaries[i]["features"] = refined_features
            break
    st.session_state["summaries"] = summaries


# ensure session keys
if "projects" not in st.session_state:
    st.session_state["projects"] = []

st.subheader("📂 GitHub Repository Loader")

# When Fetch pressed: call backend fetcher, save results to disk, then load & display
if st.button("Fetch GitHub Repositories"):
    # make sure github is always defined
    github = st.session_state["user_data"].get("github", "")
    # extract username from github field (assumes you have variable `github` from inputs)
    uname = github.strip().rstrip("/").split("/")[-1] if github else ""
    if not uname:
        st.warning("Please enter a GitHub username or URL above before fetching.")
    else:
        with st.spinner("Calling backend fetcher and saving repositories to local disk..."):
            try:
                # 1) Call backend function to fetch & analyze repos
                returned_projects = fetch_and_analyze_github(uname)
            except Exception as e:
                st.error(f"Error calling fetch_and_analyze_github: {e}")
                returned_projects = []

            # 2) Persist returned projects to data/github_repos/*.json
            if returned_projects:
                save_projects_to_disk(returned_projects)

        # 3) Always (re)load from disk to be consistent
        loaded = load_projects_from_disk()
        if not loaded:
            st.warning("No repository JSONs found on disk after fetch.")
        else:
            st.session_state["projects"] = loaded
            st.success(f"✅ Fetched and stored {len(returned_projects)} repos (loaded {len(loaded)} from disk).")
        if loaded:
            with st.spinner("Summarizing projects via LLM..."):
                summaries = []
                for r in loaded:
                    summary = summarize_project(r,target_role)
                    summaries.append(summary)
                st.session_state["summaries"] = summaries
                st.success(f"✅ Summarized {len(summaries)} projects!")

# ---------------------------
# DISPLAY SUMMARIZED PROJECTS
# ---------------------------
PROJECT_DETAILS_DIR = os.path.join(
    r"C:\Users\Harsh\Downloads\resume-agent\resume-agent-builder\data",
    "project_details"
)
os.makedirs(PROJECT_DETAILS_DIR, exist_ok=True)


# st.session_state["summaries"] = summaries

# ----------------------------------
# NEW BUTTON: Load existing fetched projects (no new API call)
# ----------------------------------
if st.button("📁 Load Fetched Projects"):
    loaded_projects = load_projects_from_disk()

    if not loaded_projects:
        st.warning("⚠️ No previously fetched projects found in local storage please first fetch the data.")
    else:
        st.session_state["projects"] = loaded_projects
        st.success(f"✅ Loaded {len(loaded_projects)} previously fetched repositories from disk.")

        # Optionally, load summarized versions if available
        summaries = []
        with st.spinner("Loading pre-summarized project details..."):
            summaries = load_existing_summaries()

        if summaries:
            st.session_state["summaries"] = summaries
            st.success(f"🧩 Loaded {len(summaries)} pre-summarized projects successfully!")
        else:
            st.info("ℹ️ No summarized project details found yet. You can refine or summarize manually.")

selected_projects = []

if st.session_state.get("summaries"):
    st.subheader("🧩 AI-Generated Project Details")

    summaries = st.session_state["summaries"]

    # Load user data (previously saved)
    user_data = load_user_projects_from_disk()


    selected_projects = []
    updated_user_data = []

    for i, proj in enumerate(summaries):
        title = proj.get("title", f"Untitled Project {i+1}")
        techs = proj.get("technologies", [])
        features = proj.get("features", [])
        # existing_entry = user_data_map.get(title, proj)

        with st.container(border=True):
            st.markdown(f"### {i+1}. **{title}**")
            st.markdown(f"**Technologies:** {', '.join(techs) or 'N/A'}")

            # --- 1️⃣ Select Checkbox ---
            is_selected = st.checkbox(f"Select '{title}' for Resume", key=f"chk_{i}")

            # --- 2️⃣ Date (Month/Year) Selector ---
            col1, col2 = st.columns(2)
            with col1:
                month = st.selectbox(
                    "Month",
                    [m for m in range(1, 13)],
                    index=(datetime.now().month - 1),
                    key=f"month_{i}"
                )
            with col2:
                year = st.selectbox(
                    "Year",
                    [y for y in range(datetime.now().year - 5, datetime.now().year + 2)],
                    index=5,
                    key=f"year_{i}"
                )
            formatted_date = f"{month:02d}/{year}"

            # --- 3️⃣ Features + Edit Mode ---
            edit_mode = st.toggle("✏️ Edit Description", key=f"edit_{i}")
            if edit_mode:
                new_features = []
                for j, feat in enumerate(features):
                    new_feat = st.text_area(f"Feature {j+1}", feat, key=f"feat_{i}_{j}")
                    new_features.append(new_feat)
                features = new_features
            else:
                for feat in features:
                    st.markdown(f"- {feat}")

            # --- 4️⃣ LLM Refinement Chat ---
            with st.expander("💬 Refine with AI"):
                refine_prompt = st.text_input(
                    "Ask LLM to modify (e.g., 'Add measurable metrics' or 'make it more technical')",
                    key=f"refine_input_{i}"
                )
                if st.button("Refine Description", key=f"refine_btn_{i}"):
                    with st.spinner("AI refining project summary..."):
                        refined = refine_project(features,target_role, refine_prompt)
                        print(refined)
                        if refined:
                            # proj = refined
                            features = refined
                            st.success("✅ Description refined successfully!")
                            refined_path = os.path.join(PROJECT_DETAILS_DIR, f"{title}.json")
                            with open(refined_path, "w", encoding="utf-8") as f:
                                json.dump({**proj, "features": refined}, f, ensure_ascii=False, indent=2)
                            update_project_in_session(title, refined)

                            st.success("✅ Description refined successfully!")
                            st.rerun()

            # Update modified project
            updated_entry = {
                "title": title,
                "technologies": techs,
                "date": formatted_date,
                "features": features
            }

            if is_selected:
                selected_projects.append(updated_entry)

            updated_user_data.append(updated_entry)

            st.markdown("---")

# # --- Finish Button: Save All User Selections + Updates ---
# if st.button("💾 Finish & Save All Changes"):
#     path = os.path.join(DATA_DIR, "user_data.json")

#     # Step 1: Load existing user data
#     if os.path.exists(path):
#         with open(path, "r", encoding="utf-8") as f:
#             try:
#                 user_data = json.load(f)
#             except Exception:
#                 user_data = {}
#     else:
#         user_data = {}

#     # Step 2: Update ONLY the "projects" field
#     user_data["projects"] = selected_projects  # <-- overwrite completely, even if empty

#     # Step 3: Save back to disk
#     try:
#         with open(path, "w", encoding="utf-8") as f:
#             json.dump(user_data, f, ensure_ascii=False, indent=2)

#         # Step 4: Sync Streamlit session state
#         st.session_state["user_data"] = user_data
#         st.session_state["user_projects"] = selected_projects

#         if selected_projects:
#             st.success(f"✅ Saved {len(selected_projects)} selected projects successfully!")
#         else:
#             st.warning("⚠️ No projects selected — cleared 'projects' section in user data.")
#     except Exception as e:
#         st.error(f"❌ Failed to update user_data.json: {e}")

# --- Finish Button: Save All User Selections + Updates ---
# if st.button("💾 Finish & Save All Changes"):
#     path = os.path.join(DATA_DIR, "user_data.json")

#     # Step 1: Load existing user data
#     if os.path.exists(path):
#         with open(path, "r", encoding="utf-8") as f:
#             try:
#                 user_data = json.load(f)
#             except Exception:
#                 user_data = {}
#     else:
#         user_data = {}

#     # ✅ Merge manual + GitHub-selected projects
#     final_projects = selected_projects + new_selected
#     user_data["projects"] = final_projects

#     # Step 3: Save back to disk
#     try:
#         with open(path, "w", encoding="utf-8") as f:
#             json.dump(user_data, f, ensure_ascii=False, indent=2)

#         # Step 4: Sync Streamlit session state
#         st.session_state["user_data"] = user_data
#         st.session_state["user_projects"] = final_projects

#         if final_projects:
#             st.success(f"✅ Saved {len(final_projects)} projects successfully!")
#         else:
#             st.warning("⚠️ No projects selected — cleared 'projects' section.")
#     except Exception as e:
#         st.error(f"❌ Failed to update user_data.json: {e}")


if st.button("💾 Finish & Save All Changes"):
    # Step 1️⃣ — Get current in-memory user_data (always most up-to-date)
    user_data = st.session_state.get("user_data", {})

    # Step 2️⃣ — Merge manual + GitHub-selected projects
    final_projects = []
    if "projects" in user_data and isinstance(user_data["projects"], list):
        # keep existing ones if you want append mode
        # existing_titles = {p.get("title", "").strip().lower() for p in user_data["projects"]}
        combined = selected_projects + new_selected
        for proj in combined:
            title = proj.get("title", "").strip().lower()
            final_projects.append(proj)
            # if title and title not in existing_titles:
            #     final_projects.append(proj)
            #     existing_titles.add(title)
        # append new ones
        user_data["projects"] = final_projects
    else:
        # if no projects yet, just assign directly
        user_data["projects"] = selected_projects + new_selected

    # Step 3️⃣ — Save to disk
    try:
        save_user_data(user_data)
        st.session_state["user_data"] = user_data

        # feedback
        total = len(user_data.get("projects", []))
        added = len(selected_projects) + len(new_selected)
        st.success(f"✅ Saved {added} new projects (total now {total}).")
    except Exception as e:
        st.error(f"❌ Failed to save projects: {e}")







# ----------------------------------
# GENERATE LATEX (optional)
# ----------------------------------

st.markdown("---")
if st.button("🧾 Generate LaTeX Resume"):
    try:
        tex = generate_resume_latex(user_data)

        with st.spinner("🤖 Checking LaTeX syntax via LLM..."):
            corrected_tex = fix_latex_syntax_with_llm(tex)

        st.subheader("✅ Generated LaTeX Code")
        st.code(corrected_tex, language="latex")

        # --- Check if pdflatex is installed ---
        pdflatex_path = shutil.which("pdflatex")

        if not pdflatex_path:
            st.warning(
                "⚠️ LaTeX compiler (`pdflatex`) not found on your system.\n\n"
                "Please install **MiKTeX** (Windows) or **TeX Live** (Linux/Mac) "
                "to enable the PDF preview feature."
            )
        else:
            # --- Compile LaTeX to PDF ---
            with st.spinner("🛠️ Compiling LaTeX to PDF..."):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tex_path = os.path.join(tmpdir, "resume.tex")
                    with open(tex_path, "w", encoding="utf-8") as f:
                        f.write(corrected_tex)

                    # Compile the LaTeX file quietly
                    result = subprocess.run(
                        ["pdflatex", "-interaction=nonstopmode", tex_path],
                        cwd=tmpdir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )

                    pdf_path = os.path.join(tmpdir, "resume.pdf")

                    if os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()

                        # --- Download buttons ---
                        st.download_button(
                            "📄 Download .tex",
                            corrected_tex,
                            "resume.tex",
                            "text/x-tex"
                        )
                        st.download_button(
                            "📘 Download PDF",
                            pdf_bytes,
                            "resume.pdf",
                            "application/pdf"
                        )

                        # --- Live PDF Preview ---
                        st.subheader("🔍 Live Resume Preview")
                        base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

                        pdf_display = f"""
                        <iframe
                            src="data:application/pdf;base64,{base64_pdf}"
                            width="100%" height="850" type="application/pdf">
                        </iframe>
                        """
                        st.markdown(pdf_display, unsafe_allow_html=True)
                    else:
                        st.error("❌ PDF generation failed. Check LaTeX syntax below:")
                        st.text(result.stderr.decode("utf-8"))

    except Exception as e:
        st.error(f"Error generating LaTeX: {e}")
