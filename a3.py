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
USERNAME = ""
PASSWORD = ""

st.set_page_config(page_title="Ask AI About RMIT", layout="wide")

with open("styles.css") as f:
  st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# === Session State ===
if "conversations" not in st.session_state:
  st.session_state.conversations = []
if "current_convo_index" not in st.session_state:
  st.session_state.current_convo_index = None

# === Helpers ===
def fetch_Data(message: str, db_path="dcnc.db"): # Change to your database name
  try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(message) # Adjust query as needed
    rows = cursor.fetchall()
    conn.close()
    return rows
  except sqlite3.Error as e:
    return [f"SQLite error: {e}"]

# Change this function based on your database schema
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
# context = """
# You are a helpful advisor for RMIT University (Royal Melbourne Institute of Technology).
# You assist students with questions about:
# - Courses and degrees
# - Admission requirements
# - Scholarships and tuition fees
# - Campus locations (Melbourne, Bundoora, Brunswick)
# - Student services (support, clubs, events)
# - Study modes (online, in-person, flexible)
# Use only current and accurate information.
# """
context = """
You are a SQL database expert. You will write SQL queries to answer questions about RMIT University courses.
You have access to a database with a database schema:
course_coordinator (
  coordinator_name VARCHAR(100) NOT NULL,
  coordinator_phone VARCHAR(20),
  coordinator_email VARCHAR(100),
  coordinator_location VARCHAR(100),
  coordinator_availability VARCHAR(50)
);

courses (
  course_name VARCHAR(100) NOT NULL,
  credit_point int,
  coordinator_name VARCHAR(100),
  description VARCHAR(255)
);

degree (
  degree_name VARCHAR(100) NOT NULL,
  level_of_study VARCHAR(50),
  student_type VARCHAR(50) NOT NULL,
  learning_mode VARCHAR(50),
  entry_score VARCHAR(50),
  duration INT,
  fees VARCHAR(50),
  next_intake VARCHAR(50),
  location VARCHAR(50)
);

degree_options (
  option_name VARCHAR(100) NOT NULL,
  degree_name VARCHAR(100) NOT NULL
);

degree_plan (
  degree_name VARCHAR(100) NOT NULL,
  plan_code VARCHAR(50) NOT NULL,
  credit_description VARCHAR(255),
  major_minor_description VARCHAR(255)
);

course_code (
  course_name VARCHAR(100) NOT NULL,
  course_code VARCHAR(10) NOT NULL,
  campus VARCHAR(50),
  career VARCHAR(50),
  school VARCHAR(50),
  learning_mode VARCHAR(50)
);

degree_core (
  degree_name VARCHAR(100) NOT NULL,
  program_year VARCHAR(50) NOT NULL,
  course_code int  NOT NULL
);

options_details (
  option_name VARCHAR(100) NOT NULL,
  option_type VARCHAR(50)
);

option_courses (
  option_name VARCHAR(100) NOT NULL,
  course_code VARCHAR(10) NOT NULL
);
Only return me the SQL query that answers the question. Do not say anything else.
"""

# === Sidebar ===
with st.sidebar:
  st.header("💬 RMIT AI Chat")
  if st.button("🆕 Start New Conversation"):
    if (
      st.session_state.current_convo_index is None
      or len(st.session_state.conversations[st.session_state.current_convo_index]["history"]) > 0
    ):
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
        course_data = fetch_Data("/Users/isaac/Desktop/dcnc.db") # Change to your database path
        course_info = format_courses_for_prompt(course_data)
        full_prompt = f"""{context}\n\n{course_info}\n\nUser Question:\n{user_input}"""
        answer = invoke_bedrock(full_prompt).strip()
        sqlresponse = fetch_Data(answer)

        st.markdown(sqlresponse)

        convo["history"].append({
          "question": user_input,
          "answer": answer
        })

        if len(convo["history"]) == 1:
          convo["title"] = user_input.capitalize()

        # st.experimental_rerun()

      except Exception as e:
        st.error(f"Error: {str(e)}")


# NEW
# import streamlit as st
# import json
# import boto3
# import sqlite3

# # === Configuration ===
# REGION = "us-east-1"
# MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
# IDENTITY_POOL_ID = "us-east-1:7771aae7-be2c-4496-a582-615af64292cf"
# USER_POOL_ID = "us-east-1_koPKi1lPU"
# APP_CLIENT_ID = "3h7m15971bnfah362dldub1u2p"
# USERNAME = "s3860650@student.rmit.edu.au"
# PASSWORD = "Dcnc123!"
# DB_PATH = "/Users/isaac/Desktop/dcnc.db"

# st.set_page_config(page_title="RMIT AI Chat", layout="wide")

# # === Session State ===
# if "messages" not in st.session_state:
#     st.session_state.messages = []

# # === Claude SQL Query Generator ===
# def get_credentials(username, password):
#     idp_client = boto3.client("cognito-idp", region_name=REGION)
#     response = idp_client.initiate_auth(
#         AuthFlow="USER_PASSWORD_AUTH",
#         AuthParameters={"USERNAME": username, "PASSWORD": password},
#         ClientId=APP_CLIENT_ID,
#     )
#     id_token = response["AuthenticationResult"]["IdToken"]

#     identity_client = boto3.client("cognito-identity", region_name=REGION)
#     identity_response = identity_client.get_id(
#         IdentityPoolId=IDENTITY_POOL_ID,
#         Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
#     )
#     creds_response = identity_client.get_credentials_for_identity(
#         IdentityId=identity_response["IdentityId"],
#         Logins={f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token},
#     )
#     return creds_response["Credentials"]

# def invoke_bedrock(prompt_text):
#     credentials = get_credentials(USERNAME, PASSWORD)
#     client = boto3.client(
#         "bedrock-runtime",
#         region_name=REGION,
#         aws_access_key_id=credentials["AccessKeyId"],
#         aws_secret_access_key=credentials["SecretKey"],
#         aws_session_token=credentials["SessionToken"],
#     )
#     payload = {
#         "anthropic_version": "bedrock-2023-05-31",
#         "max_tokens": 400,
#         "temperature": 0.7,
#         "top_p": 0.9,
#         "messages": [{"role": "user", "content": prompt_text}]
#     }
#     response = client.invoke_model(
#         body=json.dumps(payload),
#         modelId=MODEL_ID,
#         contentType="application/json",
#         accept="application/json"
#     )
#     result = json.loads(response["body"].read())
#     return result["content"][0]["text"]

# def fetch_data(sql_query, db_path=DB_PATH):
#     # if not sql_query.lower().strip().startswith("select"):
#     #     return ["Error: Unsafe query detected."]
#     try:
#         conn = sqlite3.connect(db_path)
#         cursor = conn.cursor()
#         cursor.execute(sql_query)
#         columns = [desc[0] for desc in cursor.description]
#         rows = cursor.fetchall()
#         conn.close()
#         return [dict(zip(columns, row)) for row in rows]
#     except sqlite3.Error as e:
#         return [f"SQLite error: {e}"]

# # === Claude Context ===
# context = """
# You are a SQL assistant. Based on the user's question.
# Given an input question, create a syntactically correct sql query to
# run to help find the answer. Unless the user specifies in his question a
# specific number of examples they wish to obtain, always limit your query to
# at most 20 results. You can order the results by a relevant column to
# return the most interesting examples in the database.

# Never query for all the columns from a specific table, only ask for a the
# few relevant columns given the question.

# Pay attention to use only the column names that you can see in the schema
# description. Be careful to not query for columns that do not exist. Also,
# pay attention to which column is in which table.

# return ONLY a SQL SELECT query using this database schema:

# course_coordinator (
#   coordinator_name VARCHAR(100) NOT NULL PRIMARY KEY,
#   coordinator_phone VARCHAR(20),
#   coordinator_email VARCHAR(100),
#   coordinator_location VARCHAR(100),
#   coordinator_availability VARCHAR(50)
# );

# courses (
#   course_name VARCHAR(100) NOT NULL PRIMARY KEY,
#   credit_point int,
#   coordinator_name VARCHAR(100),
#   description VARCHAR(255),
#   FOREIGN KEY (coordinator_name) REFERENCES course_coordinator(coordinator_name)
# );

# degree (
#     degree_name VARCHAR(100) NOT NULL,
#     level_of_study VARCHAR(50),
#     student_type VARCHAR(50) NOT NULL,
#     learning_mode VARCHAR(50),
#     entry_score VARCHAR(50),
#     duration INT,
#     fees VARCHAR(50),
#     next_intake VARCHAR(50),
#     location VARCHAR(50),
#     PRIMARY KEY (degree_name, student_type)
# );

# degree_options (
#   option_name VARCHAR(100) NOT NULL,
#   degree_name VARCHAR(100) NOT NULL,
#   PRIMARY KEY (option_name, degree_name)
#   FOREIGN KEY (degree_name) REFERENCES degree_plan(degree_name)
# );

# degree_plan (
#   degree_name VARCHAR(100) NOT NULL,
#   plan_code VARCHAR(50) NOT NULL,
#   credit_description VARCHAR(255),
#   major_minor_description VARCHAR(255),
#   PRIMARY KEY (degree_name, plan_code)
#   FOREIGN KEY (degree_name) REFERENCES degree(degree_name)
# );

# course_code (
#   course_name VARCHAR(100) NOT NULL,
#   course_code VARCHAR(10) NOT NULL,
#   campus VARCHAR(50),
#   career VARCHAR(50),
#   school VARCHAR(50),
#   learning_mode VARCHAR(50),
#   PRIMARY KEY (course_code, course_name),
#   FOREIGN KEY (course_name) REFERENCES courses(course_name)
# );

# degree_core (
#   degree_name VARCHAR(100) NOT NULL,
#   program_year VARCHAR(50) NOT NULL,
#   course_code int  NOT NULL,
#   PRIMARY KEY (degree_name, program_year, course_code),
#   FOREIGN KEY (degree_name) REFERENCES degree(degree_name),
#   FOREIGN KEY (course_code) REFERENCES course_code(course_code)
# );

# options_details (
#   option_name VARCHAR(100) NOT NULL PRIMARY KEY,
#   option_type VARCHAR(50)
# );

# option_courses (
#   option_name VARCHAR(100) NOT NULL,
#   course_code VARCHAR(10) NOT NULL,
#   PRIMARY KEY (option_name, course_code),
#   FOREIGN KEY (option_name) REFERENCES options_details(option_name),
#   FOREIGN KEY (course_code) REFERENCES courses(course_code)
# );


# Only return the SQL query, no additional comments. Remember: degree_core.course_code links to course_code.course_code, and that links to courses.course_name.
# """

# # === UI ===
# st.title("RMIT Student AI Chatbot")
# user_input = st.chat_input("Ask a question about RMIT courses or degrees...")

# # Display previous messages
# for msg in st.session_state.messages:
#     with st.chat_message(msg["role"]):
#         st.markdown(msg["content"])

# # Handle new input
# if user_input:
#     st.session_state.messages.append({"role": "user", "content": user_input})
#     with st.chat_message("user"):
#         st.markdown(user_input)

#     with st.chat_message("assistant"):
#         with st.spinner("Searching the database..."):
#             try:
#                 prompt = f"{context}\n\nUser question:\n{user_input}"
#                 sql_query = invoke_bedrock(prompt).strip()
#                 # result = fetch_data(sql_query)
#                 if not sql_query.lower().strip().startswith("select"):
#                     result = [f"❌ Not a valid SQL query: {sql_query}"]
#                 else:
#                     result = fetch_data(sql_query)


#                 if isinstance(result, list) and all(isinstance(row, dict) for row in result):
#                     if result:
#                         st.table(result)
#                         response = f"Here's what I found based on your question."
#                     else:
#                         response = "No data found for your query."
#                 else:
#                     response = result[0] if result else "An error occurred."

#             except Exception as e:
#                 response = f"Error: {str(e)}"

#         st.markdown(response)
#         st.session_state.messages.append({"role": "assistant", "content": response})



