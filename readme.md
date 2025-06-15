# Project Setup Instructions

Follow the steps below to set up and run this project:

1. **Create a `.env` file**
   Define your credentials by adding the following lines to a `.env` file in the root directory:

   ```env
   USERNAME=your_username
   PASSWORD=your_password
   ```

2. **Updata the Database Path**
   In chatbot.py, line 295 replace the db_path with the location of your own .db file.
   db_path = "path/to/your/chatbot.db"

3. **Ensure Python is Installed**
   Verify that Python 3.x is installed on your system. You can check this by running:

   ```bash
   python --version
   ```

   or

   ```bash
   python3 --version
   ```

4. **Create and Activate a Virtual Environment**

   - **On Windows**:

     ```bash
     python -m venv .venv
     .\.venv\Scripts\activate
     ```

   - **On macOS/Linux**:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

5. **Install Dependencies**
   Install all required packages using the `requirements.txt` file:

   ```bash
   pip install -r requirements.txt
   ```

6. **Run the Application**
   Start the Streamlit app:
   ```bash
   streamlit run chatbot.py
   ```
