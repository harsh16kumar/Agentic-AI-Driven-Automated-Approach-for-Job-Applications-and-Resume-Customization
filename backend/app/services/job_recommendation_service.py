import os
import json
import requests
from typing import List, Dict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Free keys
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")

class JobRecommendationService:
    """
    Fully free job recommender using:
    ✅ JSearch (RapidAPI free plan)
    ✅ RemoteOK (free, no key)
    ✅ Adzuna (optional free tier)
    Scoring is improved: fuzzy matching + exact matching + job title relevance.
    """

    def __init__(self):
        self.jobs_cache_path = "data/recommended_jobs.json"

    # -------------------------------------------------------
    # Extract full user profile from your resume data
    # -------------------------------------------------------
    def extract_user_profile(self, user_data: dict) -> dict:
        profile = {
            "skills": [],
            "experience_years": 0,
            "education_level": "",
            "preferred_locations": ["Remote", "India"],
            "job_titles": []
        }

        # -------------------------------------------------------
        # ✅ Extract skills (real working version)
        # -------------------------------------------------------
        skills = []

        # Direct fields
        skills += user_data.get("languages", [])
        skills += user_data.get("tools", [])
        skills += user_data.get("coursework", [])

        # Project technologies
        for p in user_data.get("projects", []):
            skills += p.get("technologies", [])

        # Extract words from experience bullet points
        for exp in user_data.get("experience", []):
            for item in exp.get("items", []):
                for word in item.split():
                    if len(word) > 3:
                        skills.append(word)

        # Normalize skills
        skills = [s.lower() for s in skills if isinstance(s, str)]
        profile["skills"] = list(set(skills))

        # -------------------------------------------------------
        # Experience years
        # -------------------------------------------------------
        profile["experience_years"] = len(user_data.get("experience", []))

        # -------------------------------------------------------
        # Education
        # -------------------------------------------------------
        education = user_data.get("education", [])
        if education:
            profile["education_level"] = education[0].get("degree", "B.Tech")

        # -------------------------------------------------------
        # Infer job titles from projects
        # -------------------------------------------------------
        inferred_titles = set()

        for proj in user_data.get("projects", []):
            t = proj.get("title", "").lower()

            if any(x in t for x in ["ml", "machine learning", "data"]):
                inferred_titles.update(["ML Engineer", "Data Scientist"])
            if any(x in t for x in ["ai", "nlp", "rag", "llm", "langchain"]):
                inferred_titles.update(["AI Engineer", "NLP Engineer"])
            if any(x in t for x in ["full stack", "backend", "web"]):
                inferred_titles.update(["Software Engineer", "Backend Engineer"])

        if not inferred_titles:
            inferred_titles = {"Software Engineer", "AI Engineer"}

        profile["job_titles"] = list(inferred_titles)

        return profile

    # -------------------------------------------------------
    # FREE API 1 — JSearch (RapidAPI free plan)
    # -------------------------------------------------------
    def search_jobs_jsearch(self, query: str, limit: int = 15) -> List[Dict]:
        if not RAPIDAPI_KEY:
            print("⚠️ RAPIDAPI_KEY missing, skipping JSearch")
            return []

        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }
        params = {"query": query, "page": 1}

        try:
            r = requests.get(url, headers=headers, params=params, timeout=8)
            data = r.json()

            jobs = []
            for job in data.get("data", []):
                jobs.append({
                    "title": job.get("job_title", ""),
                    "company": job.get("employer_name", ""),
                    "location": job.get("job_city", "") or job.get("job_country", ""),
                    "description": job.get("job_description", ""),
                    "apply_link": job.get("job_apply_link", ""),
                    "posted_date": job.get("job_posted_at_datetime_utc", ""),
                    "source": "JSearch"
                })
            return jobs

        except Exception as e:
            print("JSearch error:", e)
            return []

    # -------------------------------------------------------
    # FREE API 2 — RemoteOK (no key, free + safe)
    # -------------------------------------------------------
    def search_jobs_remoteok(self, keywords: str) -> List[Dict]:
        try:
            r = requests.get("https://remoteok.com/api", timeout=8)
            jobs_data = r.json()

            jobs = []
            for job in jobs_data[1:]:  # First entry is metadata
                title = job.get("position", "")

                if keywords.lower() in title.lower():
                    jobs.append({
                        "title": title,
                        "company": job.get("company", ""),
                        "location": job.get("location", "Remote"),
                        "description": job.get("description", ""),
                        "apply_link": job.get("url", ""),
                        "posted_date": job.get("date", ""),
                        "source": "RemoteOK"
                    })
            return jobs
        
        except Exception as e:
            print("RemoteOK error:", e)
            return []

    # -------------------------------------------------------
    # FREE API 3 — Adzuna (optional)
    # -------------------------------------------------------
    def search_jobs_adzuna(self, keywords: str) -> List[Dict]:
        if not ADZUNA_APP_ID or not ADZUNA_API_KEY:
            return []

        url = f"https://api.adzuna.com/v1/api/jobs/in/search/1"
        params = {
            "app_id": ADZUNA_APP_ID,
            "app_key": ADZUNA_API_KEY,
            "what": keywords,
            "content-type": "application/json"
        }

        try:
            r = requests.get(url, params=params, timeout=8)
            data = r.json()

            jobs = []
            for job in data.get("results", []):
                jobs.append({
                    "title": job.get("title", ""),
                    "company": job.get("company", {}).get("display_name", ""),
                    "location": job.get("location", {}).get("display_name", ""),
                    "description": job.get("description", ""),
                    "apply_link": job.get("redirect_url", ""),
                    "posted_date": job.get("created", ""),
                    "source": "Adzuna"
                })
            return jobs

        except Exception as e:
            print("Adzuna error:", e)
            return []

    # -------------------------------------------------------
    # Ranking — the FIX that makes scores non-zero
    # -------------------------------------------------------
    def rank_jobs_by_relevance(self, jobs: List[Dict], profile: dict) -> List[Dict]:
        user_skills = set(profile.get("skills", []))
        job_titles = profile.get("job_titles", [])

        # fuzzy synonyms
        synonyms = {
            "python": ["python", "pandas", "numpy", "fastapi", "flask"],
            "docker": ["docker", "container", "kubernetes", "k8s"],
            "machine learning": ["ml", "machine learning", "deep learning", "neural"],
            "ai": ["ai", "llm", "rag", "gpt", "bert"],
            "nlp": ["nlp", "transformer", "token"],
            "cloud": ["aws", "azure", "gcp", "cloud"],
            "database": ["postgres", "mysql", "mongodb", "sql"]
        }

        for job in jobs:
            score = 0
            text = (job.get("title", "") + " " + job.get("description", "")).lower()

            # ----------------------------------------
            # 1. Exact match
            # ----------------------------------------
            exact_matches = [s for s in user_skills if s in text]
            score += len(exact_matches) * 10

            # ----------------------------------------
            # 2. Fuzzy match (synonyms)
            # ----------------------------------------
            fuzzy_matches = []
            for key, words in synonyms.items():
                for w in words:
                    if w in text:
                        fuzzy_matches.append(key)
                        score += 5
                        break

            # ----------------------------------------
            # 3. Job title relevance
            # ----------------------------------------
            for title in job_titles:
                if title.lower() in job.get("title", "").lower():
                    score += 15

            # ----------------------------------------
            # Save final score
            # ----------------------------------------
            job["matched_skills"] = list(set(exact_matches + fuzzy_matches))
            job["relevance_score"] = score
            print("\n--- JOB DEBUG ---")
            print("TITLE:", job.get("title"))
            print("DESC:", job.get("description")[:300])    # first 300 chars
            print("SKILLS:", user_skills)
        return sorted(jobs, key=lambda x: x["relevance_score"], reverse=True)

    # -------------------------------------------------------
    # MAIN: Get recommended jobs
    # -------------------------------------------------------
    def get_recommended_jobs(self, user_data: dict, max_results: int = 15) -> List[Dict]:
        profile = self.extract_user_profile(user_data)
        print("🔍 Searching jobs for:", profile)

        all_jobs = []

        # Fetch jobs for top 3 inferred titles
        for title in profile["job_titles"][:3]:
            all_jobs += self.search_jobs_jsearch(title)
            all_jobs += self.search_jobs_remoteok(title)
            all_jobs += self.search_jobs_adzuna(title)

        # Remove duplicates
        unique = {}
        for job in all_jobs:
            key = (job["title"].lower(), job["company"].lower())
            if key not in unique:
                unique[key] = job

        ranked = self.rank_jobs_by_relevance(list(unique.values()), profile)

        # Save cache
        self.save_jobs_cache(ranked[:max_results])
        st.write("PROFILE DEBUG:", profile)

        return ranked[:max_results]

    # -------------------------------------------------------
    # Cache handling
    # -------------------------------------------------------
    def save_jobs_cache(self, jobs: List[Dict]):
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "jobs": jobs
        }
        os.makedirs("data", exist_ok=True)
        with open(self.jobs_cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_jobs_cache(self, max_age_hours=24):
        if not os.path.exists(self.jobs_cache_path):
            return []
        with open(self.jobs_cache_path, "r") as f:
            data = json.load(f)
        ts = datetime.fromisoformat(data["timestamp"])
        if datetime.utcnow() - ts > timedelta(hours=max_age_hours):
            return []
        return data["jobs"]
