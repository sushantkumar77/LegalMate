LegalDoc  simplifies legal drafting by turning document templates into conversations.  
Upload a `.docx`, fill placeholders via chat, and download your completed contract in seconds.

---

## 🚀 Features

- 📤 Upload `.docx` templates with placeholders like `{{ClientName}}`, `{Date}`, `[Address]`, or `<<Amount>>`
- 🔍 Automatically detects and lists all placeholders
- 💬 Chat-based interface to fill details one by one
- 🤖 Optional **Gemini API** integration for AI-powered natural questions
- 💾 Download completed `.docx` instantly
- ⚡ Works fully offline if AI is not used

---

## 🧱 Tech Stack

| Component | Technology |
|------------|-------------|
| Framework | Streamlit |
| Language | Python 3 |
| Libraries | `python-docx`, `re`, `io`, `datetime`, `streamlit` |
| Optional AI | Google Gemini API |

---

## 🧩 How It Works

1. Upload a legal or business `.docx` draft containing placeholders.  
2. LegalDoc scans and extracts placeholders automatically.  
3. The app asks questions conversationally for each field.  
4. Once all answers are collected, the completed document is generated and ready to download.  

---

## ⚙️ Installation & Setup

```bash
# 1️⃣ Clone the repository
git clone https://github.com/<your-username>/LegalDoc.git
cd LegalDoc

# 2️⃣ Run the Streamlit app
streamlit run app.py
