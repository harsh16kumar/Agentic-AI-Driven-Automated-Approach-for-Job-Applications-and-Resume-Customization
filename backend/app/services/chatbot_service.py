# backend/app/services/chatbot_service.py

import os
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import create_retrieval_chain, create_stuff_documents_chain
from langchain_groq import ChatGroq


def query_rag_response(query: str) -> str:
    """
    Query both resume and project embeddings and return an LLM-based response.
    Updated for new LangChain version (no RetrievalQA).
    """
    try:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

        resume_path = "data/embeddings/resume/resume_index.faiss"
        project_path = "data/embeddings/projects/projects_index.faiss"

        if os.path.exists(resume_path):
            db = FAISS.load_local(resume_path, embeddings, allow_dangerous_deserialization=True)
        elif os.path.exists(project_path):
            db = FAISS.load_local(project_path, embeddings, allow_dangerous_deserialization=True)
        else:
            return "No embeddings found. Please upload resume or fetch projects first."

        retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 4})

        # ✅ Groq LLM
        llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY_1"),
            model="openai/gpt-oss-120b",
            temperature=0
        )

        # ✅ Modern prompt style
        prompt = ChatPromptTemplate.from_template("""
        You are a helpful assistant using context retrieved from documents.
        If the answer cannot be found in the context, reply: "I don't know based on available data."

        Context:
        {context}

        Question:
        {input}
        """)

        # ✅ Chains replaced instead of RetrievalQA
        document_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, document_chain)

        result = rag_chain.invoke({"input": query})

        return result["answer"]

    except Exception as e:
        return f"❌ Error: {e}"
