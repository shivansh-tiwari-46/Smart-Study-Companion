# Smart Study Companion 📚🤖

An AI-powered study assistant built with Django that helps students understand concepts, summarize study material, and generate quizzes for effective learning.

## ✨ Features

- **Concept Explanation:** Get AI-generated explanations of topics.
- **Text Summarization:** Turn lengthy study material into concise summaries.
- **PDF Processing:** Upload PDF documents and extract their text for AI-assisted learning.
- **Quiz Generation:** Generate quizzes to test your understanding.
- **Study Session History:** Store study sessions in the database.

## 🛠️ Tech Stack

- **Backend:** Python, Django
- **AI Integration:** Groq API
- **PDF Processing:** pypdf
- **Frontend:** HTML, CSS, Bootstrap
- **Database:** SQLite
- **Environment Management:** python-dotenv

## ⚙️ Setup and Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/shivansh-tiwari-46/Smart-Study-Companion.git
   cd Smart-Study-Companion
   ```

2. Create and activate a virtual environment:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add your Groq API key:

   ```text
   GROQ_API_KEY=your_groq_api_key_here
   ```

5. Apply database migrations:

   ```bash
   python manage.py migrate
   ```

6. Start the development server:

   ```bash
   python manage.py runserver
   ```

7. Open `http://127.0.0.1:8000/` in your browser.

## 🔐 Security

- Keep API keys in environment variables.
- Never commit `.env` or other files containing secrets.
- Do not use Django's development server as a production server.

## 🚀 Future Improvements

- Enhanced PDF-based question answering
- Improved study history and session management
- Personalized learning recommendations
- Deployment for public access

## 👨‍💻 Author

**Shivansh Tiwari**

GitHub: [shivansh-tiwari-46](https://github.com/shivansh-tiwari-46)
