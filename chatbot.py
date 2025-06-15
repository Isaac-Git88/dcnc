import os
import json
import boto3
import sqlite3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.runnables import RunnableMap
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatAnthropic

# === Configuration ===
load_dotenv()
REGION = "us-east-1"
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
IDENTITY_POOL_ID = "us-east-1:7771aae7-be2c-4496-a582-615af64292cf"
USER_POOL_ID = "us-east-1_koPKi1lPU"
APP_CLIENT_ID = "3h7m15971bnfah362dldub1u2p"
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

st.set_page_config(page_title="Ask AI About RMIT", layout="wide")

# Load CSS
try:
    with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    pass

# === Session State ===
if "conversations" not in st.session_state:
    st.session_state.conversations = []
if "current_convo_index" not in st.session_state:
    st.session_state.current_convo_index = None
if "db_connection" not in st.session_state:
    st.session_state.db_connection = None

# === Database Helper Functions ===
def get_credentials():
    """Get AWS credentials for Bedrock"""
    idp_client = boto3.client("cognito-idp", region_name=REGION)
    response = idp_client.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": USERNAME, "PASSWORD": PASSWORD},
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

def invoke_bedrock(prompt_text, max_tokens=1000, temperature=0.1, top_p=0.9):
    """Invoke AWS Bedrock Claude model"""
    credentials = get_credentials()
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

def connect_to_database(db_path):
    """Connect to SQLite database"""
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        st.error(f"Error connecting to database: {str(e)}")
        return None

def get_database_schema(conn):
    """Get database schema information"""
    try:
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        schema_info = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()

            table_info = f"\nTable: {table_name}\n"
            table_info += "Columns:\n"
            for col in columns:
                table_info += f"  - {col[1]} ({col[2]})\n"

            schema_info.append(table_info)

        return "\n".join(schema_info)
    except Exception as e:
        return f"Error getting schema: {str(e)}"

def execute_query(conn, query):
    """Execute SQL query and return results"""
    try:
        df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        return f"SQL Error: {str(e)}"

# def get_relevant_data_context(conn, user_question):
    """Get relevant data from database based on user question"""
    try:
        context_data = []

        # Keywords to identify what type of information is needed
        question_lower = user_question.lower()

        # Course-related queries
        if any(word in question_lower for word in ['course', 'subject', 'class', 'credit']):
            courses_df = execute_query(conn, """
                SELECT c.course_name, c.credit_point, c.description,
                       cc.coordinator_name, cc.coordinator_email, cc.coordinator_phone
                FROM courses c
                LEFT JOIN course_coordinator cc ON c.coordinator_name = cc.coordinator_name
                LIMIT 50
            """)
            if isinstance(courses_df, pd.DataFrame) and not courses_df.empty:
                context_data.append("Available Courses:")
                for _, row in courses_df.iterrows():
                    context_data.append(f"- {row['course_name']} ({row['credit_point']} credits)")
                    if pd.notna(row['description']):
                        context_data.append(f"  Description: {row['description']}")
                    if pd.notna(row['coordinator_name']):
                        context_data.append(f"  Coordinator: {row['coordinator_name']} ({row['coordinator_email']})")

        # Degree-related queries
        if any(word in question_lower for word in ['degree', 'program', 'bachelor', 'master', 'diploma']):
            degrees_df = execute_query(conn, """
                SELECT degree_name, level_of_study, student_type, learning_mode,
                       entry_score, duration, fees, next_intake, location
                FROM degree
                LIMIT 30
            """)
            if isinstance(degrees_df, pd.DataFrame) and not degrees_df.empty:
                context_data.append("\nAvailable Degrees:")
                for _, row in degrees_df.iterrows():
                    context_data.append(f"- {row['degree_name']} ({row['level_of_study']})")
                    context_data.append(f"  Student Type: {row['student_type']}, Mode: {row['learning_mode']}")
                    if pd.notna(row['fees']):
                        context_data.append(f"  Fees: {row['fees']}")
                    if pd.notna(row['duration']):
                        context_data.append(f"  Duration: {row['duration']}")
                    if pd.notna(row['entry_score']):
                        context_data.append(f"  Entry Score: {row['entry_score']}")

        # Coordinator-related queries
        if any(word in question_lower for word in ['coordinator', 'contact', 'teacher', 'instructor']):
            coordinators_df = execute_query(conn, """
                SELECT coordinator_name, coordinator_email, coordinator_phone,
                       coordinator_location, coordinator_availability
                FROM course_coordinator
                LIMIT 20
            """)
            if isinstance(coordinators_df, pd.DataFrame) and not coordinators_df.empty:
                context_data.append("\nCourse Coordinators:")
                for _, row in coordinators_df.iterrows():
                    context_data.append(f"- {row['coordinator_name']}")
                    context_data.append(f"  Email: {row['coordinator_email']}")
                    if pd.notna(row['coordinator_phone']):
                        context_data.append(f"  Phone: {row['coordinator_phone']}")
                    if pd.notna(row['coordinator_location']):
                        context_data.append(f"  Location: {row['coordinator_location']}")
                    if pd.notna(row['coordinator_availability']):
                        context_data.append(f"  Availability: {row['coordinator_availability']}")

        return "\n".join(context_data) if context_data else "No specific data found for this query."

    except Exception as e:
        return f"Error retrieving data: {str(e)}"

def get_relevant_data_context(conn, user_question):
    """Generate and run SQL using LangChain and Claude."""
    try:
        # Connect LangChain to SQLite database
        db = SQLDatabase.from_uri(f"sqlite:///{conn.database}")

        # Claude model
        llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            temperature=0.7,
            max_tokens=1000,
        )

        # Define a prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that translates natural language questions into SQL for a SQLite database. The database schema is:\n{schema}"),
            ("human", "Question: {question}\nSQL Query:")
        ])

        # Create LCEL chain
        chain = (
            RunnableMap({
                "question": lambda x: x["question"],
                "schema": lambda _: db.get_table_info(),
            })
            | prompt
            | llm
            | StrOutputParser()
        )

        # Run the chain to get SQL query
        generated_sql = chain.invoke({"question": user_question})

        # Execute the generated SQL
        df = pd.read_sql_query(generated_sql, conn)

        return df.to_markdown(index=False) if not df.empty else "No data found."

    except Exception as e:
        return f"LangChain SQL error: {str(e)}"



def process_user_query(user_input, db_path):
    """Process user query with database context"""
    try:
        conn = connect_to_database(db_path)
        if not conn:
            return "Unable to connect to the database. Please check the database path."

        # Get database schema
        schema = get_database_schema(conn)

        # Get relevant data based on the question
        relevant_data = get_relevant_data_context(conn, user_input)

        # Create comprehensive prompt
        prompt = f"""
You are an expert RMIT University advisor helping students with their questions about courses, degrees, and academic information.

DATABASE SCHEMA:
{schema}

RELEVANT DATA FROM DATABASE:
{relevant_data}

STUDENT QUESTION: {user_input}

Instructions:
1. Answer the student's question using the database information provided
2. Be helpful, accurate, and student-friendly
3. Include specific details like course names, credit points, coordinator contacts, fees, etc. when relevant
4. If the information isn't available in the data provided, just be honest
5. Format your response clearly with proper spacing and organization
6. Always provide actionable information when possible

Please provide a comprehensive answer to the student's question:
"""

        response = invoke_bedrock(prompt)
        conn.close()
        return response

    except Exception as e:
        return f"I apologize, but I encountered an error processing your question: {str(e)}"

# === Sidebar ===
with st.sidebar:
    st.header("💬 RMIT AI Chat")

    # Database path input
    db_path = "/Users/isaac/Desktop/chatbot.db"

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
st.title("RMIT Student AI Advisor")
st.markdown("*Intelligent database-powered assistance for RMIT students*")

# Chat container
chat_container = st.container()

# Input box
user_input = st.chat_input("Ask me anything about RMIT courses, degrees, or coordinators...")

# Show messages if a conversation exists
if st.session_state.current_convo_index is not None:
    convo = st.session_state.conversations[st.session_state.current_convo_index]

    with chat_container:
        for entry in convo["history"]:
            with st.chat_message("user"):
                st.markdown(entry["question"])
            with st.chat_message("assistant"):
                st.markdown(entry["answer"])

# Process user input
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
        with st.spinner("Searching database and generating response..."):
            try:
                answer = process_user_query(user_input, db_path)
                st.markdown(answer)

                convo["history"].append({
                    "question": user_input,
                    "answer": answer
                })

                # Update conversation title
                # if len(convo["history"]) == 1:
                #     convo["title"] = user_input[:50] + "..." if len(user_input) > 50 else user_input
                if len(convo["history"]) == 1:
                  convo["title"] = user_input.capitalize()

                st.rerun()

            except Exception as e:
                error_msg = f"I apologize, but I encountered an error: {str(e)}"
                st.error(error_msg)

                convo["history"].append({
                    "question": user_input,
                    "answer": error_msg
                })

# === Example Questions Section ===
if st.session_state.current_convo_index is None or len(st.session_state.conversations[st.session_state.current_convo_index]["history"]) == 0:
    st.markdown("---")
    st.subheader("💡 Example Questions You Can Ask:")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **About Courses:**
        - What courses are available in Computer Science?
        - Who is the coordinator for Machine Learning?
        - Show me all courses with their coordinators
        """)

    with col2:
        st.markdown("""
        **About Degrees:**
        - What degrees are available for international students?
        - Show me all degrees with online learning mode
        - What are the fees for Computer Science degrees?
        """)

    st.markdown("""
    **About Coordinators:**
    - Contact details for Dr. Smith
    - When is the AI coordinator available?
    - List all coordinators in Melbourne campus
    """)
