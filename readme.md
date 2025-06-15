# Project Setup Instructions

Follow the steps below to set up and run this project:

1. **Create a `.env` file**
   Define your credentials by adding the following lines to a `.env` file in the root directory:

   ```env
   USERNAME=your_username
   PASSWORD=your_password
   ```

2. **Ensure Python is Installed**
   Verify that Python 3.x is installed on your system. You can check this by running:

   ```bash
   python --version
   ```

   or

   ```bash
   python3 --version
   ```

3. **Create and Activate a Virtual Environment**

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

4. **Install Dependencies**
   Install all required packages using the `requirements.txt` file:

   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Application**
   Start the Streamlit app:
   ```bash
   streamlit run chatbot.py
   ```
