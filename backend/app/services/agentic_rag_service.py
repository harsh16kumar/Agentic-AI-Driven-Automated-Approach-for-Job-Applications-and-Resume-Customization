import os
import random
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

# ===== Helper to get random LLM key =====
def get_random_llm(model="openai/gpt-oss-120b", temperature=0.7):
    api_keys = [
        os.getenv("GROQ_API_KEY_1"),
        os.getenv("GROQ_API_KEY_2"),
        os.getenv("GROQ_API_KEY_3"),
        os.getenv("GROQ_API_KEY_4"),
        os.getenv("GROQ_API_KEY_5"),
    ]
    key = random.choice([k for k in api_keys if k])
    return ChatGroq(api_key=key, model=model, temperature=temperature)


# ===== 1️⃣ ROUTER AGENT (LLM-A) =====
def route_query(user_query: str) -> str:
    """
    Uses LLM-A to decide whether to use 'resume' or 'project' embeddings.
    """
    llm = get_random_llm()
    prompt = f"""
    You are a routing AI deciding which knowledge base is most relevant to the user query.
    Knowledge bases available:
    1. resume — contains user's education, skills, and experiences.
    2. project — contains GitHub project details and technical summaries.

    Query: "{user_query}"

    Decide which knowledge base(s) to use. Answer with either:
    "resume", "project", or "both".
    """

    resp = llm.invoke(prompt)
    answer = getattr(resp, "content", str(resp)).strip().lower()
    if "project" in answer and "resume" in answer:
        return "both"
    elif "project" in answer:
        return "project"
    else:
        return "resume"


# ===== 2️⃣ RETRIEVER NODE =====
def retrieve_answer(user_query: str, source: str) -> str:
    """
    Retrieves context and generates a response from the chosen FAISS embedding.
    """
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    llm = get_random_llm(temperature=0.6)

    resume_path = "data/embeddings/resume/resume_index"
    project_path = "data/embeddings/projects/projects_index"

    dbs = []
    if source in ["resume", "both"] and os.path.exists(resume_path):
        dbs.append(FAISS.load_local(resume_path, embeddings, allow_dangerous_deserialization=True))
    if source in ["project", "both"] and os.path.exists(project_path):
        dbs.append(FAISS.load_local(project_path, embeddings, allow_dangerous_deserialization=True))

    if not dbs:
        return "⚠️ No embeddings found for the selected source."

    # Combine if both are needed
    if len(dbs) > 1:
        all_docs = []
        for db in dbs:
            all_docs.extend(db.similarity_search(user_query, k=4))
        context = "\n\n".join([doc.page_content for doc in all_docs])
    else:
        context = "\n\n".join([doc.page_content for doc in dbs[0].similarity_search(user_query, k=4)])

    prompt = f"""
    You are an AI assistant answering user queries based on provided context.

    Context:
    {context}

    Question:
    {user_query}

    Provide a clear, factual, well-structured answer.
    """

    resp = llm.invoke(prompt)
    return getattr(resp, "content", str(resp))


# ===== 3️⃣ GRADER AGENT (LLM-B) =====
def grade_answer(user_query: str, answer: str) -> tuple:
    """
    Uses another LLM (LLM-B) to check if the answer satisfies the query.
    Returns (bool, feedback).
    """
    llm = get_random_llm(temperature=0.0)
    prompt = f"""
    You are a strict answer evaluator.

    Question: {user_query}
    Answer: {answer}

    Evaluate if the answer fully and accurately addresses the user's question.
    Reply with JSON:
    {{
      "grade": "pass" or "fail",
      "feedback": "why you graded it so"
    }}
    """
    resp = llm.invoke(prompt)
    text = getattr(resp, "content", str(resp))

    import json, re
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            result = json.loads(match.group(0))
            return (result.get("grade", "fail") == "pass", result.get("feedback", ""))
        except:
            return (False, "Invalid grader output")
    return (False, "Could not parse grader response.")


# ===== MAIN PIPELINE =====
def agentic_rag_pipeline(user_query: str) -> str:
    """
    Orchestrates Agentic RAG flow: router → retriever → grader → loop if needed.
    """
    source = route_query(user_query)
    answer = retrieve_answer(user_query, source)
    passed, feedback = grade_answer(user_query, answer)

    if not passed:
        # Retry once with adjusted reasoning
        correction_prompt = f"Your last answer was graded as insufficient because: {feedback}. Please correct it."
        llm = get_random_llm()
        resp = llm.invoke(correction_prompt)
        answer = getattr(resp, "content", str(resp))

    return answer
