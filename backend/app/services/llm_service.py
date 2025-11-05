import os
import json
from langchain_groq import ChatGroq 
from dotenv import load_dotenv
from datetime import datetime
import random
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
        model="openai/gpt-oss-20b",
        temperature=0.7
    )
    return llm



PROJECT_DETAILS_DIR = os.path.join("data", "project_details")
os.makedirs(PROJECT_DETAILS_DIR, exist_ok=True)

import os
import json
from datetime import datetime

PROJECT_DETAILS_DIR = os.path.join("data", "project_details")
os.makedirs(PROJECT_DETAILS_DIR, exist_ok=True)

import os
import json

PROJECT_DETAILS_DIR = os.path.join("data", "project_details")
os.makedirs(PROJECT_DETAILS_DIR, exist_ok=True)

# -------------------------------------------------------------
# SUB-FUNCTION 1: Generate Project Title
# -------------------------------------------------------------
def generate_project_title(repo_name, readme, files, llm):
    llm = get_random_llm()
    prompt = f"""
    You are an expert AI system that generates professional, descriptive project titles for GitHub repositories.

    Repository name: {repo_name}
    README (if present): {readme[:1200]}
    File names: {', '.join(files[:30])}

    Rules:
    - The title must sound professional, concise, and suitable for a resume.
    - Use contextual hints (e.g., "langchain" + "chatbot" → "Agentic Chatbot using LangChain").
    - Format: “Descriptive Title using [Core Technologies or Concepts]”.
    - Word count should be between 3-5.
    - Return only the title text, nothing else.
    """

    try:
        response = llm.invoke(prompt)
        title = getattr(response, "content", str(response)).strip().replace('"', '')
        print("title:",title)
        return title
    except Exception as e:
        print(f"[ERROR] Title generation failed for {repo_name}: {e}")
        return repo_name.replace("_", " ").title()


# -------------------------------------------------------------
# SUB-FUNCTION 2: Extract Technologies
# -------------------------------------------------------------
def extract_technologies(requirements, files, llm):
    llm = get_random_llm()
    prompt = f"""
    You are a specialized AI model that extracts technologies, frameworks, and libraries used in a project.

    Given:
    - Requirements.txt content: {requirements}
    - File names: {files[:40]}

    Task:
    - Identify and list all relevant technologies (e.g., Python, LangChain, TensorFlow, Flask, React).
    - If no technology is explicitely mentioned then based on topics and all the names and words listed generate and guess the technologies that might have been used.
    - If tech count exceeds 5 then ONLY follow following rules:
        = Count only major technologies and most critical one especially those which are rare.
        = Also if you see under the umbrella 2 technologies or tools or software are used replace by major one like pandas , numpy , seaborn can come under python.
    - Return a JSON array of strings only, e.g. ["Python", "LangChain", "FastAPI"].
    """

    try:
        response = llm.invoke(prompt)
        techs = json.loads(getattr(response, "content", str(response)))
        if isinstance(techs, list):
            return techs
    except Exception as e:
        print(f"[WARN] Tech extraction failed: {e}")
    # fallback
    return []

# -------------------------------------------------------------
# SUB-FUNCTION 3: Generate Project Features
# -------------------------------------------------------------

def generate_project_features(title, techs, readme, files, role, llm):
    llm = get_random_llm()
    prompt = f"""
    You are an expert technical resume writer with deep understanding of how to present projects attractively for recruiters.

    INPUTS:
    - A JSON object containing the following fields:
    {{
        "repository": "{title}",
        "readme": "{readme[:1000].replace('"', "'")}",
        "requirements": [{', '.join(f'"{t}"' for t in techs)}],
        "files_name": [{', '.join(f'"{f}"' for f in files[:20])}],
        "role": "{role}"
    }}

    TASK:
    1. Analyze the provided repository details to infer the purpose, functionality, and technical depth of the project.
    2. Based on the "role" field, generate exactly **3 resume-ready bullet points** that:
    - Emphasize relevant technical and analytical skills.
    - Highlight design, implementation, and impact aspects.
    - Sound sophisticated and recruiter-attractive.
    - Are concise (one line each), professional, and in active voice.
    3. Adapt the language to match the role (for example, emphasize analytics and data insight for a Data Scientist, or backend architecture for a Software Engineer).

    OUTPUT FORMAT:
    Return strictly valid JSON:
    {{
    "features": [
        "bullet point 1",
        "bullet point 2",
        "bullet point 3"
    ]
    }}

    No extra commentary or markdown — only the JSON object.
    """

    try:
        response = llm.invoke(prompt)

        # Get raw text output (works for both object and string)
        raw_output = getattr(response, "content", str(response))

        # Attempt to parse JSON safely
        parsed = json.loads(raw_output)

        if isinstance(parsed, dict) and "features" in parsed:
            return parsed["features"]

    except Exception as e:
        print(f"[WARN] Feature generation failed: {e}")

    # Fallback response
    return [
        "Developed a software project using modern technologies.",
        "Implemented multiple functionalities inferred from repository structure.",
        "Generated fallback summary due to LLM output issue."
    ]

    


# -------------------------------------------------------------
# MAIN FUNCTION: Summarize Project (modular composition)
# -------------------------------------------------------------
def summarize_project(repo,role, llm=None):
    llm = get_random_llm()
    if llm is None:
        from backend.app.services.llm_service import llm

    repo_name = repo.get("repository") or repo.get("repo") or repo.get("name") or "UnnamedRepo"
    readme = repo.get("readme", "")
    requirements = repo.get("requirements", "")
    files = repo.get("files_name", [])

    # 1️⃣ Generate Project Title
    title = generate_project_title(repo_name, readme, files, llm)

    # 2️⃣ Extract Technologies
    techs = extract_technologies(requirements, files, llm)

    # 3️⃣ Generate 3 Features
    features = generate_project_features(title, requirements, readme, files,role, llm)

    # 4️⃣ Combine into final JSON
    data = {
        "title": title,
        "technologies": techs,
        "date": "",
        "features": features
    }

    # 5️⃣ Save to Disk
    safe_name = "".join(c for c in repo_name if c.isalnum() or c in ("-", "_")).rstrip()
    out_path = os.path.join(PROJECT_DETAILS_DIR, f"{safe_name}.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] ✅ Saved summary to {out_path}")
    except Exception as e:
        print(f"[WARN] Could not save summary for {repo_name}: {e}")

    return data


def refine_project(features: list[str],role, user_msg: str):
    llm = get_random_llm()
    """
    Refines only the list of project features based on user feedback.
    Returns a refined features list (same structure, no type errors).
    """
    # Build clear prompt for the LLM
    prompt = f"""
    The following are bullet-point features describing a project:

    {json.dumps(features, indent=2)}

    User request: "{user_msg}"

    Rewrite or refine these features to make them better, 
    following these rules:
    - Tailoe the features based on role given by user {role}.
    - Keep the same list structure (a JSON list of strings).
    - Keep each feature concise (1–2 lines max).
    - Maintain a professional, resume-style tone.

    Return **only** the refined JSON list (no markdown, no extra text).
    """

    # Call your LLM
    resp = llm.invoke(prompt)

    # Parse the response safely
    try:
        refined_features = json.loads(resp.content)
        if not isinstance(refined_features, list):
            raise ValueError("Response is not a JSON list")
    except Exception:
        refined_features = features  # fallback to original if parsing fails

    return refined_features


def fix_latex_syntax_with_llm(latex_code: str) -> str:
    """Send LaTeX code to LLM to fix only syntax issues (balanced braces, etc.)."""
    llm = get_random_llm()
    prompt = f"""
    You are a LaTeX syntax validator and fixer.
    Check only for missing or extra braces, unbalanced environments,
    and similar structure errors. Do not change content or wording.
    Adds '\' before reserved symbols and escapes special sequences.

    Return the corrected LaTeX code only — no explanations, no markdown fences.

    LaTeX code:
    {latex_code}
    """

    try:
        response = llm.invoke(prompt)

        # --- Extract only the corrected text ---
        corrected = ""
        if hasattr(response, "content"):
            corrected = response.content
        elif isinstance(response, dict) and "content" in response:
            corrected = response["content"]
        elif isinstance(response, dict) and "text" in response:
            corrected = response["text"]
        else:
            corrected = str(response)

        # Remove code fences if present
        corrected = corrected.strip().strip("`")
        corrected = corrected.replace("```latex", "").replace("```", "").strip()

        return corrected

    except Exception as e:
        # st.warning(f"LLM syntax check failed: {e}")
        return latex_code

def refine_text(data, user_msg):
    llm = get_random_llm()
    """
    Refine any structured content (project, achievement, etc.) using AI.
    Keeps the same JSON structure.
    """
    prompt = f"""
    You are an expert assistant. Refine the following structured JSON data while preserving its structure and meaning.
    Make only linguistic or clarity improvements based on the user request.
    
    Current JSON data:
    {json.dumps(data, indent=2)}
    
    User request: {user_msg}
    
    Return the updated JSON data only, keeping the same keys and structure.
    """

    try:
        resp = llm.invoke(prompt)  # assuming same LLM call used in your app
        refined = json.loads(resp) if isinstance(resp, str) else resp

        # Safety check: ensure structure remains same
        if isinstance(refined, dict) and set(refined.keys()) == set(data.keys()):
            return refined
        else:
            # fallback: return refined only if structure is compatible
            return refined if isinstance(refined, dict) else data

    except Exception as e:
        # st.error(f"❌ Refinement failed: {e}")
        return data


