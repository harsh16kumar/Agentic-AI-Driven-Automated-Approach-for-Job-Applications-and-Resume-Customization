# import requests
# from typing import List, Dict

# # Keep the prior heuristics and README extraction logic here.

# def fetch_github_repos(username: str) -> List[Dict]:
#     url = f"https://api.github.com/users/{username}/repos"
#     resp = requests.get(url)
#     if resp.status_code != 200:
#         print(f"GitHub API error: {resp.status_code}")
#         return []
#     return resp.json()

# def fetch_repo_files(owner: str, repo: str) -> List[str]:
#     url = f"https://api.github.com/repos/{owner}/{repo}/contents"
#     resp = requests.get(url)
#     if resp.status_code != 200:
#         return []
#     return [f["name"] for f in resp.json() if f["type"] == "file"]

# def fetch_readme(owner: str, repo: str) -> str:
#     url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
#     resp = requests.get(url)
#     if resp.status_code == 200:
#         return resp.text
#     url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
#     resp = requests.get(url)
#     if resp.status_code == 200:
#         return resp.text
#     return ""

# def analyze_project(owner: str, repo: str) -> Dict:
#     files = fetch_repo_files(owner, repo)
#     project_info = {
#         "repo": repo,
#         "summary": "",
#         "features": [],
#         "packages": [],
#         "technologies": []
#     }

#     # Basic heuristics
#     if "package.json" in files:
#         project_info["features"].append("Node/React Project")
#         url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/package.json"
#         resp = requests.get(url)
#         if resp.status_code == 200:
#             try:
#                 content = resp.json()
#                 deps = list(content.get("dependencies", {}).keys())
#                 project_info["packages"].extend(deps)
#             except Exception:
#                 pass

#     if "requirements.txt" in files:
#         project_info["features"].append("Python Project")
#         url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/requirements.txt"
#         resp = requests.get(url)
#         if resp.status_code == 200:
#             pkgs = [p.strip() for p in resp.text.splitlines() if p.strip()]
#             project_info["packages"].extend(pkgs)

#     # fetch README for summary (non-LLM fallback)
#     readme_text = fetch_readme(owner, repo)
#     if readme_text:
#         # simple heuristic summary: first non-empty paragraph
#         paragraphs = [p.strip() for p in readme_text.split("\n\n") if p.strip()]
#         project_info["summary"] = paragraphs[0][:800] if paragraphs else ""

#         # try to capture tech mentions (simple heur)
#         techs = []
#         keywords = ["django", "flask", "react", "node", "express", "tensorflow", "torch", "keras", "sklearn"]
#         lower = readme_text.lower()
#         for k in keywords:
#             if k in lower:
#                 techs.append(k)
#         project_info["technologies"] = list(set(techs))

#     # identify deep-learning by packages
#     dl_keywords = ["torch", "tensorflow", "keras", "sklearn"]
#     if any(any(k in pkg.lower() for k in dl_keywords) for pkg in project_info["packages"]):
#         project_info["features"].append("Deep Learning Project")

#     return project_info

# def fetch_and_analyze_github(username: str) -> List[Dict]:
#     repos = fetch_github_repos(username)
#     projects = []
#     for r in repos:
#         name = r.get("name")
#         projects.append(analyze_project(username, name))
#     return projects
import requests
import base64
import ast
import json
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

# ========== CONFIG ==========
EXCLUDED_DIRS = {"venv", "__pycache__", "node_modules", "dist", "build", ".git"}
INCLUDE_EXTENSIONS = {".py", ".js", ".ts", ".ipynb", ".java"}
MAX_FILE_SIZE = 50000          # bytes (50 KB)
MAX_LINES = 100                # lines per file
OUTPUT_DIR = "data/github_repos"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
# =============================


# ---------- CORE FETCHERS ----------

def fetch_github_repos(username: str) -> List[Dict]:
    url = f"https://api.github.com/users/{username}/repos"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch repos: {resp.status_code}")
        return []
    data = resp.json()
    print(f"[INFO] Found {len(data)} repositories for '{username}'.")
    return data


def fetch_repo_contents(owner: str, repo: str, path: str = "", all_files: List[str] = None) -> List[Dict]:
    """Recursively fetch contents of a repository and record *all* file names."""
    if all_files is None:
        all_files = []

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"[WARN] Cannot fetch '{path}' in '{repo}' (HTTP {resp.status_code})")
        return []

    data = resp.json()
    filtered_files = []

    for item in data:
        if item["type"] == "dir":
            # Record the directory name in all_files too (for full structure if needed)
            fetch_repo_contents(owner, repo, item["path"], all_files)
        elif item["type"] == "file":
            all_files.append(item["path"])  # ✅ record every file, regardless of filter
            ext = os.path.splitext(item["name"])[1].lower()
            if ext in INCLUDE_EXTENSIONS and item["size"] <= MAX_FILE_SIZE:
                # filter only relevant files for deeper analysis
                if not any(ex in item["path"].lower() for ex in EXCLUDED_DIRS):
                    filtered_files.append(item)
    return filtered_files


# ---------- FILE UTILITIES ----------

def fetch_file_text(item: Dict) -> str:
    """Fetch file content using download_url or Base64 API fallback."""
    url = item.get("download_url")
    if url:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.text

    api_url = item.get("url")
    if api_url:
        resp = requests.get(api_url, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return ""


# ---------- MAIN ANALYZER ----------

def analyze_repository(owner: str, repo: str) -> Dict:
    print(f"\n[INFO] 🔍 Analyzing repository '{repo}'...")

    repo_data = {
        "repository": repo,
        "readme": "",
        "requirements": "",
        "files_name": []
    }

    # --- Fetch top-level README and requirements.txt ---
    for file_name in ["README.md", "readme.md"]:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{file_name}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            repo_data["readme"] = resp.text
            break

    for req_file in ["requirements.txt", "setup.py"]:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{req_file}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            repo_data["requirements"] = resp.text
            break

    all_files_collector = []
    filtered_files = fetch_repo_contents(owner, repo, "", all_files_collector)
    repo_data["files_name"] = all_files_collector  # ✅ store all file names

    return repo_data


# ---------- ENTRY POINT ----------

def fetch_and_analyze_github(username: str):
    repos = fetch_github_repos(username)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for r in repos:
        repo_name = r.get("name")
        save_path = os.path.join(OUTPUT_DIR, f"{repo_name}.json")

        # ✅ Skip repo if JSON already exists
        if os.path.exists(save_path):
            print(f"[SKIP] 💤 '{repo_name}' already analyzed. Skipping...")
            # Optionally, load the data instead of re-fetching
            with open(save_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            results.append(existing_data)
            continue

        # Otherwise analyze normally
        analysis = analyze_repository(username, repo_name)
        results.append(analysis)

        # Save the new analysis
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        print(f"[SAVED] 💾 {save_path}")

    return results


# def fetch_and_analyze_github(username: str) -> List[Dict]:
#     repos = fetch_github_repos(username)
#     projects = []
#     for r in repos:
#         name = r.get("name")
#         projects.append(analyze_project(username, name))
#     return projects


if __name__ == "__main__":
    username = input("Enter GitHub username: ").strip()
    all_results = fetch_and_analyze_github(username)
    print(f"\n[INFO] Analysis complete for {len(all_results)} repositories.")
