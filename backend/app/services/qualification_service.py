# backend/app/services/qualification_service.py

import os
import re
import json
import smtplib
from datetime import datetime
from email.message import EmailMessage
import streamlit as st
import sys

sys.path.append(r"C:\Users\Harsh\Downloads\Q_A_Chatbot_Using_Agentic_RAG_Architecture\q_a_chatbot\backend\app\services")

from user_data_service import load_user_data, save_user_data


# -----------------------------------
# ✉️ EMAIL FUNCTION (GMAIL APP PASSWORD)
# -----------------------------------
def send_email_gmail(subject: str, body: str):
    """
    Send email to candidate using Gmail App Password.
    - Receiver email is automatically fetched from user_data.json
    - Sender details are stored in .env
    """
    # Load candidate data
    user_data = load_user_data()
    receiver_email = (
        user_data.get("contact", {}).get("email")
        or user_data.get("email")
    )


    if not receiver_email:
        st.error("❌ Candidate email not found in user_data.json — cannot send email.")
        return False

    # Load sender credentials
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASS = os.getenv("EMAIL_PASS")
    FROM_EMAIL = os.getenv("FROM_EMAIL", EMAIL_USER)

    if not EMAIL_USER or not EMAIL_PASS:
        st.error("❌ Missing EMAIL_USER or EMAIL_PASS in .env — cannot send email.")
        return False

    msg = EmailMessage()
    msg["From"] = FROM_EMAIL
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        st.success(f"📧 Email sent to {receiver_email}")
        return True
    except Exception as e:
        st.error(f"❌ Failed to send email: {e}")
        return False


# -----------------------------------
# 🤖 QUALIFICATION CHECK FUNCTION
# -----------------------------------
def verify_and_notify_qualification(parsed_data: dict, cgpa: str, skill: str, llm, threshold: int = 60):
    """
    Verifies that CGPA and skill match the resume contents using LLM.
    Saves result, sends email if valid, returns result dict.
    """
    resume_text = json.dumps(parsed_data, ensure_ascii=False, indent=2)

    prompt = f"""
        You are a professional resume verifier.
        Check if the candidate's declared qualifications align with their resume.first check for cgpa if it passes then go for skill checking.
        for skill checking check with skills , projects and every data available ... there might be cases where candidate didnt mention skill in
        skill column but projects and other things show that he has skill . so use your intelligence to check for skills.

        Candidate-declared data:
        - CGPA: "{cgpa}"
        - Key Skill: "{skill}"

        Resume JSON:
        {resume_text}

        Provide your analysis in **strict JSON only** like this:
        {{
        "decision": "Pass" or "Fail",
        "score": integer (0-100),
        "reason": "short one-line justification"
        }}
        """

    # --------------------------
    # Step 1: Run LLM grading
    # --------------------------
    with st.spinner("🤖 Checking qualifications using AI..."):
        try:
            resp = llm.invoke(prompt)
            text = getattr(resp, "content", str(resp))
            match = re.search(r'\{[\s\S]*\}', text)
            data = json.loads(match.group(0)) if match else json.loads(text)
            decision = data.get("decision", "").title()
            score = int(data.get("score", 0))
            reason = data.get("reason", "")
        except Exception as e:
            st.error(f"❌ LLM verification failed: {e}")
            return None

    # --------------------------
    # Step 2: Save Result
    # --------------------------
    user_data = load_user_data()
    user_data["qualification_result"] = {
        "decision": decision,
        "score": score,
        "reason": reason,
        "checked_at": datetime.utcnow().isoformat() + "Z"
    }
    save_user_data(user_data)
    st.session_state["user_data"] = user_data

    st.success(f"✅ Qualification Check: {decision} (Score: {score})")
    st.info(reason)

    # --------------------------
    # Step 3: Send Email (if passed)
    # --------------------------
    if decision == "Pass" or score >= threshold:
        subject = "🎉 Qualification Verified Successfully!"
        body = f"""
            Hello {parsed_data.get("name", "Candidate")},

            Your qualification has been verified successfully!

            Result: {decision}
            Score: {score}
            Reason: {reason}

            We're impressed with your profile — expect further communication soon! 🚀

            Warm regards,  
            The Agentic Resume Team
            """
        send_email_gmail(subject, body)
    else:
        st.warning("❌ Qualification not in accordance. No email sent.")

    return {
        "decision": decision,
        "score": score,
        "reason": reason
    }