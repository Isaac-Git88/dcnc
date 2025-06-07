import streamlit as st
import json
import boto3
import sqlite3

# === Configuration ===
REGION = "us-east-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
IDENTITY_POOL_ID = "us-east-1:7771aae7-be2c-4496-a582-615af64292cf"
USER_POOL_ID = "us-east-1_koPKi1lPU"
APP_CLIENT_ID = "3h7m15971bnfah362dldub1u2p"
USERNAME = "s3860650@student.rmit.edu.au"
PASSWORD = "Dcnc123!"

st.set_page_config(page_title="Ask AI About RMIT", layout="wide")

with open("styles.css") as f:
  st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# === Session State ===
if "conversations" not in st.session_state:
  st.session_state.conversations = []
if "current_convo_index" not in st.session_state:
  st.session_state.current_convo_index = None

# === Helpers ===
def fetch_Data(db_path="a3.db"):
  try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, course_coordinator, credits FROM Course;")
    rows = cursor.fetchall()
    conn.close()
    return rows
  except sqlite3.Error as e:
    return [f"SQLite error: {e}"]

def format_courses_for_prompt(courses):
  if not courses or isinstance(courses[0], str):
    return "No course data available or error reading database."
  lines = ["Available RMIT Courses:"]
  for name, coordinator, credits in courses:
    lines.append(f"- {name} (Coordinator: {coordinator}, Credits: {credits})")
  return "\n".join(lines)

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

# === Base Context for Prompt ===
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

# === Sidebar ===
with st.sidebar:
  st.header("💬 RMIT AI Chat")
  if st.button("🆕 Start New Conversation"):
    new_index = len(st.session_state.conversations)
    st.session_state.conversations.append({
      "title": f"Conversation {new_index + 1}",
      "history": []
    })
    st.session_state.current_convo_index = new_index
  st.subheader("Chat History")
  for i, convo in enumerate(st.session_state.conversations):
    if st.button(convo["title"], key=f"load_{i}"):
      st.session_state.current_convo_index = i

# === Main Chat Display Area ===
st.title("📘 RMIT Student AI Advisor")

# Chat container at the top
chat_container = st.container()

# Input box at bottom
user_input = st.chat_input("Ask something...")

# Show messages if a conversation exists
if st.session_state.current_convo_index is not None:
  convo = st.session_state.conversations[st.session_state.current_convo_index]

  with chat_container:
    for entry in convo["history"]:
      with st.chat_message("user"):
        st.markdown(entry["question"])
      with st.chat_message("assistant"):
        st.markdown(entry["answer"])

# When user submits a message
if user_input:
  if st.session_state.current_convo_index is None:
    st.session_state.conversations.append({
      "title": "Untitled",
      "history": []
    })
    st.session_state.current_convo_index = 0

  convo = st.session_state.conversations[st.session_state.current_convo_index]

  with st.chat_message("user"):
    st.markdown(user_input)

  with st.chat_message("assistant"):
    with st.spinner("Thinking..."):
      try:
        course_data = fetch_Data("/Users/isaac/Downloads/a3.db")
        course_info = format_courses_for_prompt(course_data)
        full_prompt = f"""{context}\n\n{course_info}\n\nUser Question:\n{user_input}"""
        answer = invoke_bedrock(full_prompt).strip()
        st.markdown(answer)

        convo["history"].append({
          "question": user_input,
          "answer": answer
        })

        if len(convo["history"]) == 1:
          convo["title"] = user_input.capitalize()

      except Exception as e:
        st.error(f"Error: {str(e)}")
