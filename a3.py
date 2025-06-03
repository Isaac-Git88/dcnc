# RMIT Student AI Advisor with Live Web Info
# Author: Cyrus Gao, Xiang Li | Updated: June 2025

import streamlit as st
import json
import boto3
import requests
from bs4 import BeautifulSoup

# === AWS Configuration === #
REGION = "us-east-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
IDENTITY_POOL_ID = "us-east-1:7771aae7-be2c-4496-a582-615af64292cf"
USER_POOL_ID = "us-east-1_koPKi1lPU"
APP_CLIENT_ID = "3h7m15971bnfah362dldub1u2p"
USERNAME = ""
PASSWORD = ""


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


# === Helper: Call Claude === #
def invoke_bedrock(prompt_text, max_tokens=640, temperature=0.7, top_p=0.9):
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


# === Helper: Scrape RMIT Web Info === #
def get_live_info():
    try:
        urls = {
            "RMIT": "https://www.rmit.edu.au",
        }
        result = ""

        for label, url in urls.items():
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            cleaned = "\n".join(text.splitlines()[:25])
            result += f"\n--- {label.upper()} ---\n{cleaned}\n"

        return result.strip()
    except Exception as e:
        return f"[Error fetching live RMIT info: {str(e)}]"


# === Streamlit UI === #
st.set_page_config(page_title="Ask AI About RMIT", layout="centered")
st.title("\U0001F4DA RMIT Student Advisor")
st.markdown("Ask anything about RMIT courses, campus life.")

# Base static context
context = """
You are a helpful advisor for RMIT University (Royal Melbourne Institute of Technology).
You assist students with questions about:
- Courses and degrees
- Admission requirements
- Scholarships and tuition fees
- Campus locations (Melbourne, Bundoora, Brunswick)
- Student services (support, clubs, events)
- Study modes (online, in-person, flexible)
Use only current and accurate information.
"""

st.subheader("Ask a Question")
user_question = st.text_input("Type your question below:", placeholder="e.g., What are the prerequisites for Cyber Security?")

if st.button("Get Answer"):
    if not user_question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Fetching live data and thinking..."):
            try:
                live_info = get_live_info()
                full_prompt = f"{context}\n\nLatest RMIT Website Info:\n{live_info}\n\nUser Question: {user_question}"
                answer = invoke_bedrock(full_prompt)
                st.success("Here’s the answer:")
                st.text_area("Claude's Answer", value=answer.strip(), height=300)
            except Exception as e:
                st.error(f"Error: {str(e)}")
