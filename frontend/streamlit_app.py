import os
import sys
import json
import re
import random
import shutil
import base64
import tempfile
import subprocess
from typing import Dict, List
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import fitz  # PyMuPDF

# ===============================
# PATHS & PYTHONPATH
# ===============================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ---- Your requested data dir (macOS path) ----
DATA_DIR = r"/Users/anirudhsharma/Desktop/Agentic-AI-Driven-Automated-Approach-for-Job-Applications-and-Resume-Customization/frontend/data"
USER_DATA_PATH = os.path.join(DATA_DIR, "user_data.json")
GITHUB_REPO_PATH = os.path.join(DATA_DIR, "github_repos")
PROJECT_DETAILS_DIR = os.path.join(DATA_DIR, "project_details")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GITHUB_REPO_PATH, exist_ok=True)
os.makedirs(PROJECT_DETAILS_DIR, exist_ok=True)

# ===============================
# BACKEND IMPORTS
# ===============================
from backend.app.services.github_service import fetch_and_analyze_github
from backend.app.services.llm_service import summarize_project, fix_latex_syntax_with_llm
from backend.app.services.latex_service import generate_resume_latex
from backend.app.services.job_recommendation_service import JobRecommendationService
from backend.app.services.job_application_service import JobApplicationService
from project_refine_modal import refine_project  # your refine helper

# ===============================
# ENV & LLM
# ===============================
load_dotenv()
API_KEYS = [os.getenv(f"GROQ_API_KEY_{i}") for i in range(1, 6)]

def get_random_llm():
    key = random.choice([k for k in API_KEYS if k])
    return ChatGroq(api_key=key, model="openai/gpt-oss-120b", temperature=0.7)

# ===============================
# HELPERS: USER DATA & PROJECTS
# ===============================
def load_user_data() -> Dict:
    if os.path.exists(USER_DATA_PATH):
        try:
            with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_data(data: Dict):
    with open(USER_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def update_user_data(key: str, value):
    st.session_state["user_data"][key] = value
    save_user_data(st.session_state["user_data"])

def update_from_resume(parsed_data: dict):
    st.session_state["user_data"] = parsed_data
    save_user_data(parsed_data)
    st.success("✅ Resume data replaced successfully!")

def save_projects(projects: List[Dict]):
    for p in projects:
        repo_name = p.get("repository") or p.get("repo") or p.get("name") or "unknown_repo"
        safe_name = "".join(c for c in repo_name if c.isalnum() or c in "-_")
        path = os.path.join(GITHUB_REPO_PATH, f"{safe_name or 'repo'}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

def load_local_projects() -> List[Dict]:
    projects = []
    if not os.path.exists(GITHUB_REPO_PATH):
        return projects
    for f in os.listdir(GITHUB_REPO_PATH):
        if f.endswith(".json"):
            try:
                with open(os.path.join(GITHUB_REPO_PATH, f), "r", encoding="utf-8") as file:
                    projects.append(json.load(file))
            except Exception:
                pass
    return projects

def save_projects_to_disk(projects: List[Dict]):
    for p in projects:
        repo_name = p.get("repository") or p.get("repo") or p.get("name") or "unknown_repo"
        safe_name = "".join(c for c in repo_name if c.isalnum() or c in ("-", "_")).rstrip() or "repo"
        out_path = os.path.join(GITHUB_REPO_PATH, f"{safe_name}.json")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.warning(f"Failed to save {repo_name} -> {e}")

def load_projects_from_disk() -> List[Dict]:
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

def load_existing_summaries() -> List[Dict]:
    summaries = []
    if not os.path.exists(PROJECT_DETAILS_DIR):
        st.warning(f"⚠️ Project details folder not found: {PROJECT_DETAILS_DIR}")
        return summaries

    files = sorted([f for f in os.listdir(PROJECT_DETAILS_DIR) if f.endswith(".json")])
    if not files:
        return summaries

    for fname in files:
        full_path = os.path.join(PROJECT_DETAILS_DIR, fname)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "title" in data:
                    summaries.append(data)
        except Exception as e:
            st.error(f"❌ Failed to load {fname}: {e}")
    return summaries

def update_project_in_session(title: str, refined_features: list):
    summaries = st.session_state.get("summaries", [])
    for i, proj in enumerate(summaries):
        if proj.get("title") == title:
            summaries[i]["features"] = refined_features
            break
    st.session_state["summaries"] = summaries

def load_user_projects_from_disk():
    if os.path.exists(USER_DATA_PATH):
        with open(USER_DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# ===============================
# INIT STATE
# ===============================
if "user_data" not in st.session_state:
    st.session_state["user_data"] = load_user_data()
if "projects" not in st.session_state:
    st.session_state["projects"] = []
if "modal_open" not in st.session_state:
    st.session_state["modal_open"] = False

user_data = st.session_state["user_data"]
llm = get_random_llm()

# ===============================
# UI — HEADER & ROLE
# ===============================
st.set_page_config(page_title="Agentic Resume Builder", layout="centered")
st.title("Agentic Resume Builder — Streamlit Frontend")

role_value = st.text_input(
    "🎯 Target role (used to tailor project bullets)",
    value=user_data.get("role", ""),
    key="target_role_input"
)
if role_value != user_data.get("role", ""):
    update_user_data("role", role_value)
target_role = st.session_state["user_data"].get("role", "")

# ===============================
# MODE: UPLOAD OR CREATE
# ===============================
st.header("1) Choose: Upload resume or Create from scratch")
mode = st.radio("Mode", ["Upload PDF resume", "Create from scratch"])

# ---- Upload Mode ----
if mode == "Upload PDF resume":
    uploaded = st.file_uploader("📄 Upload your resume (PDF)", type=["pdf"])
    if uploaded:
        save_path = os.path.join(DATA_DIR, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.success(f"✅ Saved file to {save_path}")

        with st.spinner("🔍 Extracting text from resume..."):
            pdf_doc = fitz.open(save_path)
            pdf_text = "".join(page.get_text("text") for page in pdf_doc)
            pdf_doc.close()

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
                response_text = getattr(resp, "content", str(resp))
                match = re.search(r'\{[\s\S]*\}', response_text)
                cleaned_json = match.group(0) if match else response_text.strip()
                parsed_data = json.loads(cleaned_json)

                # Normalize lists
                for key in ["education", "experience", "projects", "achievements"]:
                    if isinstance(parsed_data.get(key), dict):
                        parsed_data[key] = [parsed_data[key]]
                    elif key not in parsed_data:
                        parsed_data[key] = []

                update_from_resume(parsed_data)
                st.success("✅ Resume data extracted and saved successfully!")
                with st.expander("🧾 Preview Extracted Data"):
                    st.json(parsed_data)

            except json.JSONDecodeError:
                st.error("❌ The AI response was not valid JSON. Try re-uploading or check resume formatting.")
                st.text(response_text)
            except Exception as e:
                st.error(f"❌ Failed to extract resume fields: {e}")

# ---- Create from Scratch ----
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

    st.subheader("Education (add multiple)")
    saved_edu = user_data.get("education", [])
    edu_cnt = st.number_input("Number of education entries", min_value=1, max_value=5, value=len(saved_edu) or 1, key="edu_cnt")
    education = []
    for i in range(int(edu_cnt)):
        prev = saved_edu[i] if i < len(saved_edu) else {}
        with st.expander(f"Education #{i+1}", expanded=(i == 0)):
            institution = st.text_input(f"Institution #{i+1}", value=prev.get("institution", ""), key=f"inst_{i}")
            period = st.text_input("Period (e.g., 2020 -- 2024)", value=prev.get("period", ""), key=f"period_{i}")
            degree = st.text_input("Degree", value=prev.get("degree", ""), key=f"degree_{i}")
            cgpa = st.text_input("CGPA", value=prev.get("cgpa", ""), key=f"cgpa_{i}")
            location = st.text_input("City, Country", value=prev.get("location", ""), key=f"loc_{i}")
            education.append({"institution": institution, "period": period, "degree": degree, "cgpa": cgpa, "location": location})
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
            city = st.text_input("City", value=prev.get("city", ""), key=f"ecity_{i}")
            country = st.text_input("Country", value=prev.get("country", ""), key=f"ecountry_{i}")
            start = st.text_input("Start Date", value=prev.get("start", ""), key=f"estart_{i}")
            end = st.text_input("End Date", value=prev.get("end", ""), key=f"eend_{i}")
            role = st.text_input("Role", value=prev.get("role", ""), key=f"erole_{i}")
            items = st.text_area("Bullet points (one per line)", value="\n".join(prev.get("items", [])), key=f"eitems_{i}")
            experience.append({
                "company": company, "role": role, "start": start, "end": end,
                "city": city, "country": country,
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
                "title": title, "link": link, "category": category,
                "items": [l.strip() for l in items.splitlines() if l.strip()]
            })
    update_user_data("achievements", achievements)

# ===============================
# PROJECTS (MANUAL)
# ===============================
st.subheader("Projects (Manual Entry)")
saved_projects = user_data.get("projects", [])
proj_cnt = st.number_input("Number of projects to enter manually", min_value=0, max_value=10, value=len(saved_projects) or 0, key="proj_cnt_manual")

manual_projects = []
for i in range(int(proj_cnt)):
    prev = saved_projects[i] if i < len(saved_projects) else {}
    with st.expander(f"Project #{i+1}", expanded=(i == 0)):
        title = st.text_input("Project Title", value=prev.get("title", ""), key=f"mtitle_{i}")
        tech_raw = st.text_input("Technologies (comma separated)", value=", ".join(prev.get("technologies", [])), key=f"mtech_{i}")
        technologies = [t.strip() for t in tech_raw.split(",") if t.strip()]
        col1, col2 = st.columns(2)
        with col1:
            month = st.selectbox("Month", [m for m in range(1, 13)], key=f"mmonth_{i}")
        with col2:
            year = st.selectbox("Year", [y for y in range(datetime.now().year - 5, datetime.now().year + 2)], key=f"myear_{i}")
        formatted_date = f"{month:02d}/{year}"
        features_text = st.text_area("Features (bullet points, one per line)", value="\n".join(prev.get("features", [])), key=f"mfeat_{i}")
        features = [f.strip() for f in features_text.splitlines() if f.strip()]
        is_selected = st.checkbox(f"Select '{title}' for Resume", key=f"mselect_{i}")
        manual_projects.append({
            "title": title, "technologies": technologies, "date": formatted_date,
            "features": features, "selected": is_selected
        })
new_selected = [p for p in manual_projects if p["selected"] and p["title"]]

# ===============================
# GITHUB FETCH & SUMMARIZE
# ===============================
st.subheader("📂 GitHub Repository Loader")

if st.button("Fetch GitHub Repositories"):
    github_field = st.session_state["user_data"].get("github", "")
    uname = github_field.strip().rstrip("/").split("/")[-1] if github_field else ""
    if not uname:
        st.warning("Please enter a GitHub username or URL above before fetching.")
    else:
        with st.spinner("Calling backend fetcher and saving repositories to local disk..."):
            try:
                returned_projects = fetch_and_analyze_github(uname)
            except Exception as e:
                st.error(f"Error calling fetch_and_analyze_github: {e}")
                returned_projects = []

            if returned_projects:
                save_projects_to_disk(returned_projects)

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
                    try:
                        summaries.append(summarize_project(r, target_role))
                    except Exception as e:
                        st.warning(f"Skipped one repo: {e}")
                st.session_state["summaries"] = summaries
                st.success(f"✅ Summarized {len(summaries)} projects!")

if st.button("📁 Load Fetched Projects"):
    loaded_projects = load_projects_from_disk()
    if not loaded_projects:
        st.warning("⚠️ No previously fetched projects found in local storage; please fetch first.")
    else:
        st.session_state["projects"] = loaded_projects
        st.success(f"✅ Loaded {len(loaded_projects)} previously fetched repositories from disk.")
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
    _user_data_disk = load_user_projects_from_disk()

    for i, proj in enumerate(summaries):
        title = proj.get("title", f"Untitled Project {i+1}")
        techs = proj.get("technologies", [])
        features = proj.get("features", [])

        with st.container(border=True):
            st.markdown(f"### {i+1}. **{title}**")
            st.markdown(f"**Technologies:** {', '.join(techs) or 'N/A'}")
            is_selected = st.checkbox(f"Select '{title}' for Resume", key=f"chk_{i}")

            col1, col2 = st.columns(2)
            with col1:
                month = st.selectbox("Month", [m for m in range(1, 13)], index=(datetime.now().month - 1), key=f"month_{i}")
            with col2:
                year = st.selectbox("Year", [y for y in range(datetime.now().year - 5, datetime.now().year + 2)], index=5, key=f"year_{i}")
            formatted_date = f"{month:02d}/{year}"

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

            with st.expander("💬 Refine with AI"):
                refine_prompt = st.text_input(
                    "Ask LLM to modify (e.g., 'Add measurable metrics' or 'make it more technical')",
                    key=f"refine_input_{i}"
                )
                if st.button("Refine Description", key=f"refine_btn_{i}"):
                    with st.spinner("AI refining project summary..."):
                        refined = refine_project(features, target_role, refine_prompt)
                        if refined:
                            features = refined
                            st.success("✅ Description refined successfully!")
                            refined_path = os.path.join(PROJECT_DETAILS_DIR, f"{title}.json")
                            with open(refined_path, "w", encoding="utf-8") as f:
                                json.dump({**proj, "features": refined}, f, ensure_ascii=False, indent=2)
                            update_project_in_session(title, refined)
                            st.rerun()

            updated_entry = {"title": title, "technologies": techs, "date": formatted_date, "features": features}
            if is_selected:
                selected_projects.append(updated_entry)

# ===============================
# SAVE SELECTED & MANUAL PROJECTS
# ===============================
if st.button("💾 Finish & Save All Changes"):
    user_data = st.session_state.get("user_data", {})
    combined = selected_projects + new_selected
    user_data["projects"] = combined
    try:
        save_user_data(user_data)
        st.session_state["user_data"] = user_data
        total = len(user_data.get("projects", []))
        added = len(combined)
        st.success(f"✅ Saved {added} projects (total now {total}).")
    except Exception as e:
        st.error(f"❌ Failed to save projects: {e}")

# ===============================
# 💼 JOB RECOMMENDATIONS & AUTO-APPLY  (NEW SECTION)
# ===============================
st.markdown("---")
st.header("💼 AI-Powered Job Recommendations & Auto-Apply")

# Services
job_rec_service = JobRecommendationService()
job_app_service = JobApplicationService()

user_data = st.session_state.get("user_data", {})
if not user_data.get("name"):
    st.warning("⚠️ Please complete your resume details above first (at least your name).")
else:
    st.success(f"👤 Profile loaded for: {user_data.get('name')}")

    # ---- Recommendations ----
    st.subheader("🔍 Find Recommended Jobs")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("Click below to fetch the latest jobs matching your profile")
    with col2:
        fetch_jobs = st.button("🚀 Fetch Jobs", type="primary")

    if fetch_jobs:
        with st.spinner("🔍 Searching for jobs across multiple platforms..."):
            try:
                cached_jobs = job_rec_service.load_jobs_cache(max_age_hours=24)
                if cached_jobs:
                    st.info("📦 Loaded jobs from cache (less than 24 hours old)")
                    recommended_jobs = cached_jobs
                else:
                    recommended_jobs = job_rec_service.get_recommended_jobs(user_data, max_results=15)
                st.session_state["recommended_jobs"] = recommended_jobs
                st.success(f"✅ Found {len(recommended_jobs)} relevant job opportunities!")
            except Exception as e:
                st.error(f"❌ Error fetching jobs: {e}")

    # ---- Display & Filters ----
    if "recommended_jobs" in st.session_state and st.session_state["recommended_jobs"]:
        st.subheader(f"📋 {len(st.session_state['recommended_jobs'])} Recommended Jobs")
        col1, col2, col3 = st.columns(3)
        with col1:
            min_score = st.slider("Min Relevance Score", 0, 100, 0)
        with col2:
            source_filter = st.multiselect(
                "Source",
                options=sorted(list(set([j.get("source", "Unknown") for j in st.session_state["recommended_jobs"]]))),
                default=[]
            )
        with col3:
            company_search = st.text_input("Search Company", "")

        filtered_jobs = st.session_state["recommended_jobs"]
        if min_score > 0:
            filtered_jobs = [j for j in filtered_jobs if j.get("relevance_score", 0) >= min_score]
        if source_filter:
            filtered_jobs = [j for j in filtered_jobs if j.get("source", "") in source_filter]
        if company_search:
            filtered_jobs = [j for j in filtered_jobs if company_search.lower() in j.get("company", "").lower()]

        st.session_state["selected_jobs"] = []
        for idx, job in enumerate(filtered_jobs):
            with st.expander(f"🏢 {job.get('title')} at {job.get('company')} | Score: {job.get('relevance_score', 0)}"):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**Location:** {job.get('location', 'N/A')}")
                    st.markdown(f"**Posted:** {job.get('posted_date', 'N/A')}")
                    st.markdown(f"**Source:** {job.get('source', 'Unknown')}")
                    if job.get("matched_skills"):
                        st.markdown(f"**Matched Skills:** {', '.join(job['matched_skills'][:5])}")
                    desc = job.get("description", "")
                    st.markdown(f"**Description:** {desc[:300] + '...' if len(desc) > 300 else desc}")
                    if job.get("apply_link"):
                        st.markdown(f"[🔗 View Job Posting]({job.get('apply_link')})")
                with c2:
                    selected = st.checkbox("Select for Auto-Apply", key=f"job_select_{idx}")
                    if selected:
                        st.session_state["selected_jobs"].append(job)

        st.info(f"✅ {len(st.session_state.get('selected_jobs', []))} jobs selected for application")

        # ---- Auto-Apply ----
        st.divider()
        st.subheader("🤖 Automated Job Applications")

        if st.session_state.get("selected_jobs"):
            st.warning("⚠️ **Important:** Automated application may require LinkedIn credentials and can trigger security checks. Use at your own risk.")

            with st.form("auto_apply_form"):
                st.markdown("### LinkedIn Credentials (Optional)")
                st.caption("Required for LinkedIn Easy Apply jobs. Leave empty to skip LinkedIn jobs.")
                linkedin_email = st.text_input("LinkedIn Email", type="default")
                linkedin_password = st.text_input("LinkedIn Password", type="password")
                max_applications = st.slider("Max Applications", 1, 10, 3)
                headless = st.checkbox("Run in headless mode (no browser window)", value=False)
                submit_applications = st.form_submit_button("🚀 Start Auto-Apply", type="primary")

            if submit_applications:
                with st.spinner(f"🤖 Applying to {len(st.session_state['selected_jobs'][:max_applications])} jobs..."):
                    try:
                        job_app_service.headless = headless
                        results = job_app_service.apply_to_jobs(
                            jobs=st.session_state["selected_jobs"],
                            user_data=user_data,
                            linkedin_email=linkedin_email if linkedin_email else None,
                            linkedin_password=linkedin_password if linkedin_password else None,
                            max_applications=max_applications
                        )
                        st.success("✅ Application process completed!")
                        success_count = sum(1 for r in results if r.get("status") == "success")
                        st.metric("Successful Applications", success_count)

                        for result in results:
                            status_emoji = "✅" if result.get("status") == "success" else "⚠️" if result.get("status") == "partial" else "❌"
                            st.markdown(f"{status_emoji} **{result.get('job_title')}** at {result.get('company')} - {result.get('status')}")
                    except Exception as e:
                        st.error(f"❌ Application error: {e}")
        else:
            st.info("👆 Select jobs above to enable auto-apply")

        # ---- History ----
        st.divider()
        st.subheader("📜 Application History")
        if st.button("📂 Load Application History"):
            history = job_app_service.get_application_history()
            if history:
                st.success(f"Found {len(history)} past applications")
                for app in history[-10:]:
                    status_emoji = "✅" if app.get("status") == "success" else "⚠️" if app.get("status") == "partial" else "❌"
                    with st.expander(f"{status_emoji} {app.get('job_title')} at {app.get('company')}"):
                        st.json(app)
            else:
                st.info("No application history found")

# ===============================
# GENERATE LATEX (optional)
# ===============================
st.markdown("---")
if st.button("🧾 Generate LaTeX Resume"):
    try:
        tex = generate_resume_latex(st.session_state.get("user_data", {}))
        with st.spinner("🤖 Checking LaTeX syntax via LLM..."):
            corrected_tex = fix_latex_syntax_with_llm(tex)
        st.subheader("✅ Generated LaTeX Code")
        st.code(corrected_tex, language="latex")

        pdflatex_path = shutil.which("pdflatex")
        if not pdflatex_path:
            st.warning(
                "⚠️ LaTeX compiler (`pdflatex`) not found on your system.\n\n"
                "Please install **MacTeX** (macOS), **TeX Live** (Linux), or **MiKTeX** (Windows) to enable the PDF preview feature."
            )
        else:
            with st.spinner("🛠️ Compiling LaTeX to PDF..."):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tex_path = os.path.join(tmpdir, "resume.tex")
                    with open(tex_path, "w", encoding="utf-8") as f:
                        f.write(corrected_tex)

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

                        st.download_button("📄 Download .tex", corrected_tex, "resume.tex", "text/x-tex")
                        st.download_button("📘 Download PDF", pdf_bytes, "resume.pdf", "application/pdf")

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
