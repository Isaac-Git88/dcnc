# Cyber Security Course Advisor via AWS Bedrock
# Author: Cyrus Gao, extended by Xiang Li
# Updated: May 2025

import streamlit as st
import json
import boto3
from datetime import datetime
from PyPDF2 import PdfReader

# === AWS Configuration === #
REGION = "us-east-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
IDENTITY_POOL_ID = "us-east-1:7771aae7-be2c-4496-a582-615af64292cf"
USER_POOL_ID = "us-east-1_koPKi1lPU"
APP_CLIENT_ID = "3h7m15971bnfah362dldub1u2p"
USERNAME = "" # Replace with your username
PASSWORD = ""    # Replace with your password


# === Helper: Get AWS Credentials === #
def get_credentials(username, password):
    idp_client = boto3.client("cognito-idp", region_name=REGION)
    response = idp_client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
        ClientId=APP_CLIENT_ID,
    )
    id_token = response["AuthenticationResult"]["IdToken"]

    identity_client = boto3.client("cognito-identity", region_name=REGION)
    identity_response = identity_client.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
    )

    creds_response = identity_client.get_credentials_for_identity(
        IdentityId=identity_response["IdentityId"],
        Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
    )

    return creds_response["Credentials"]


# === Helper: Build Prompt from JSON + Structure === #
def build_prompt(courses, user_question, structure=None):
    course_dict = {c["title"]: c for c in courses}

    structure_text = ""
    if structure and "recommended_courses" in structure:
        structure_text += "### Recommended Study Plan by Year:\n"
        for year, course_titles in structure["recommended_courses"].items():
            structure_text += f"**{year.replace('_', ' ').title()}**:\n"
            for title in course_titles:
                course = course_dict.get(title)
                if course:
                    structure_text += f"- {title} ({course['course_code']})\n"
                else:
                    structure_text += f"- {title} (not found in course list)\n"
            structure_text += "\n"

    course_list = []
    for course in courses:
        title = course.get("title", "Untitled")
        code = course.get("course_code", "N/A")
        desc = course.get("description", "No description available.")
        course_type = course.get("course_type", "N/A")
        minor = course.get("minor_track", [])
        minor_info = f", Minor: {minor[0]}" if minor else ""
        course_text = f"- {title} ({code}): {desc}\n  Type: {course_type}{minor_info}"
        course_list.append(course_text)
    full_course_context = "\n".join(course_list)

    prompt = (
        "You are a helpful assistant that supports students in selecting courses from the "
        "Bachelor of Cyber Security program at RMIT (codes BP355/BP356). "
        "Recommend only from the official course list. Each course is categorized as core, capstone, minor, or elective. "
        "Use the recommended structure to suggest suitable courses based on study year and interest.\n\n"
        + structure_text
        + "\n### All Available Courses:\n"
        + full_course_context
        + "\n\nUser:\n" + user_question
    )
    return prompt


# === Helper: Extract text from multiple PDFs === #
def extract_text_from_pdfs(pdf_files):
    all_text = []
    for pdf_file in pdf_files:
        try:
            reader = PdfReader(pdf_file)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    all_text.append(text.strip())
        except Exception as e:
            all_text.append(f"[Error reading file {pdf_file.name}: {str(e)}]")
    return "\n\n".join(all_text)


# === Helper: Invoke Claude via Bedrock === #
def invoke_bedrock(prompt_text, max_tokens=640, temperature=0.3, top_p=0.9):
    credentials = get_credentials(USERNAME, PASSWORD)

    bedrock_runtime = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretKey"],
        aws_session_token=credentials["SessionToken"],
    )

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "messages": [{"role": "user", "content": prompt_text}]
    }

    response = bedrock_runtime.invoke_model(
        body=json.dumps(payload),
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json"
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


# === Streamlit UI === #
st.set_page_config(page_title="RMIT Cyber Security Course Advisor", layout="centered")

st.title("\U0001F393 Cyber Security Course Advisor")
st.markdown("This assistant helps students in RMIT's Bachelor of Cyber Security (BP355/BP356) choose courses.")

st.subheader("Step 1: Choose your data input format")
upload_mode = st.radio("Select format:", ["Structured JSON files", "Unstructured PDF files"])

if upload_mode == "Structured JSON files":
    uploaded_courses_json = st.file_uploader("\U0001F4C1 Upload `courses_data.json`", type=["json"], key="courses")
    uploaded_structure_json = st.file_uploader("\U0001F4C1 Upload `cyber_security_program_structure.json`", type=["json"], key="structure")
    uploaded_pdfs = None
else:
    uploaded_pdfs = st.file_uploader("\U0001F4C4 Upload one or more PDF files", type=["pdf"], accept_multiple_files=True)
    uploaded_courses_json = None
    uploaded_structure_json = None

st.subheader("Step 2: Ask a question")
user_question = st.text_input(
    "\U0001F4AC What would you like to ask?",
    placeholder="e.g., I'm a second-year student interested in digital forensics and blockchain."
)

if st.button("\U0001F4A1 Get Advice"):
    if not user_question:
        st.warning("Please enter a question.")
    elif upload_mode == "Structured JSON files" and (not uploaded_courses_json or not uploaded_structure_json):
        st.warning("Please upload both JSON files.")
    elif upload_mode == "Unstructured PDF files" and not uploaded_pdfs:
        st.warning("Please upload at least one PDF file.")
    else:
        try:
            if upload_mode == "Structured JSON files":
                courses = json.load(uploaded_courses_json)
                structure = json.load(uploaded_structure_json)
                prompt = build_prompt(courses, user_question, structure)
            else:
                extracted_text = extract_text_from_pdfs(uploaded_pdfs)
                prompt = (
                    "You are a course advisor. The following is extracted from official course documents:\n\n"
                    + extracted_text +
                    "\n\nPlease answer the following question based on this information:\n"
                    + user_question
                )

            with st.spinner("\U0001F50D Generating advice..."):
                answer = invoke_bedrock(prompt)
                st.success("\u2705 Response received")
                st.text_area("\U0001F916 Claude's Answer", answer, height=300)

        except Exception as e:
            st.error(f"\u274C Error: {str(e)}")
