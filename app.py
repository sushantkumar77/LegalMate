import streamlit as st
import re
import io
import google.generativeai as genai
from docx import Document
import os
from datetime import datetime
from dotenv import load_dotenv
import json

load_dotenv()

st.set_page_config(
    page_title="Legal Document Processor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { padding: 0rem 1rem; }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        font-weight: 600;
        background-color: #007bff;
        color: white;
    }
    .upload-section {
        border: 2px dashed #4CAF50;
        border-radius: 10px;
        padding: 2rem;
        text-align: center;
        background-color: #f0f8ff;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #007bff;
        color: white;
        margin-left: 20%;
    }
    .assistant-message {
        background-color: #e9ecef;
        color: #212529;
        margin-right: 20%;
    }
    .placeholder-box {
        padding: 0.8rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        border-left: 4px solid;
    }
    .completed { background-color: #d4edda; border-color: #28a745; color: #155724; }
    .current { background-color: #cce5ff; border-color: #007bff; color: #004085; }
    .pending { background-color: #f8f9fa; border-color: #dee2e6; color: #6c757d; }
    .success-box {
        padding: 1.5rem;
        border-radius: 10px;
        background-color: #d4edda;
        border: 2px solid #28a745;
        text-align: center;
    }
    .doc-preview {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 10px;
        border: 2px solid #dee2e6;
        max-height: 500px;
        overflow-y: auto;
        font-family: 'Courier New', monospace;
        white-space: pre-wrap;
        color: #212529;
    }
</style>
""", unsafe_allow_html=True)

# Initialize ALL session state variables first
if 'step' not in st.session_state:
    st.session_state.step = 'upload'
if 'placeholders' not in st.session_state:
    st.session_state.placeholders = []
if 'filled_data' not in st.session_state:
    st.session_state.filled_data = {}
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'current_index' not in st.session_state:
    st.session_state.current_index = 0
if 'document_text' not in st.session_state:
    st.session_state.document_text = ""
if 'file_name' not in st.session_state:
    st.session_state.file_name = ""
if 'completed_doc' not in st.session_state:
    st.session_state.completed_doc = ""
if 'api_configured' not in st.session_state:
    st.session_state.api_configured = False
if 'waiting_for_clarification' not in st.session_state:
    st.session_state.waiting_for_clarification = False
if 'model_name' not in st.session_state:
    st.session_state.model_name = None

# Get API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
if not GEMINI_API_KEY:
    try:
        GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
    except:
        pass

# Configure API once
if GEMINI_API_KEY and not st.session_state.api_configured:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Try different model names
        model_options = [
            'gemini-1.5-flash',
            'gemini-1.5-pro', 
            'gemini-pro',
            'models/gemini-1.5-flash',
            'models/gemini-pro'
        ]
        
        for model_name in model_options:
            try:
                test_model = genai.GenerativeModel(model_name)
                # Test with a simple prompt
                test_model.generate_content("Hi")
                st.session_state.model_name = model_name
                st.session_state.api_configured = True
                break
            except:
                continue
                
        if not st.session_state.api_configured:
            st.error("Could not find a working Gemini model. Please check your API key.")
            
    except Exception as e:
        st.error(f"API configuration failed: {str(e)}")

def parse_docx(file):
    """Parse DOCX file and extract text"""
    try:
        doc = Document(file)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        st.error(f"Error parsing DOCX: {str(e)}")
        return ""

def detect_placeholders_with_ai(text):
    """Use Gemini AI to intelligently detect placeholders"""
    if not st.session_state.api_configured or not st.session_state.model_name:
        st.error("❌ Gemini API not configured properly")
        return []
    
    try:
        model = genai.GenerativeModel(st.session_state.model_name)
        
        prompt = f"""You are analyzing a legal document to find ALL placeholders that need user input.

DOCUMENT TEXT:
{text}

TASK: Find every placeholder. Look for:
1. Text in brackets: [Company Name], {{Investor}}, <Date>
2. Underscores that need filling: _________ (only if 5+ chars)
3. Dollar brackets: ${{Amount}}
4. Keywords: INSERT, FILL IN, [TBD]

RULES:
- Each placeholder must be unique and meaningful
- Ignore very short underscores (under 5 chars)
- Order by appearance in document
- Extract clear labels

OUTPUT (valid JSON only, no markdown):
{{
  "placeholders": [
    {{
      "label": "Company Name",
      "original": "[Company Name]",
      "description": "Legal name of company",
      "position": 145
    }}
  ]
}}

Return ONLY the JSON."""

        response = model.generate_content(prompt)
        ai_text = response.text.strip()
        
        # Clean JSON
        if '```json' in ai_text:
            ai_text = ai_text.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_text:
            ai_text = ai_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(ai_text)
        
        placeholders = []
        seen_labels = set()
        
        for item in result.get('placeholders', []):
            label = item['label'].strip()
            
            if label in seen_labels or label.lower() in ['the', 'and', 'or', 'insert', 'a', 'an']:
                continue
            
            seen_labels.add(label)
            key = re.sub(r'[^a-z0-9]', '_', label.lower())
            
            placeholders.append({
                'key': key,
                'label': label,
                'original': item['original'],
                'description': item.get('description', ''),
                'value': '',
                'position': item.get('position', len(placeholders))
            })
        
        return sorted(placeholders, key=lambda x: x['position'])
        
    except Exception as e:
        st.error(f"AI detection failed: {str(e)}")
        return []

def get_ai_question(placeholder, filled_data):
    """Generate contextual question for placeholder"""
    if not st.session_state.api_configured:
        return f"What should I use for {placeholder['label']}?"
    
    try:
        model = genai.GenerativeModel(st.session_state.model_name)
        
        doc_text = st.session_state.document_text
        pos = doc_text.find(placeholder['original'])
        if pos >= 0:
            context_start = max(0, pos - 150)
            context_end = min(len(doc_text), pos + 150)
            context = doc_text[context_start:context_end]
        else:
            context = ""
        
        filled_info = "\n".join([
            f"- {p['label']}: {filled_data.get(p['key'], 'not filled')}"
            for p in st.session_state.placeholders[:st.session_state.current_index]
        ]) if filled_data else "This is the first field."
        
        prompt = f"""Generate ONE clear question to ask for this information.

PLACEHOLDER: {placeholder['label']}
APPEARS AS: {placeholder['original']}

CONTEXT: ...{context}...

FILLED: {filled_info}

RULES:
1. ONE question under 20 words
2. Include examples if helpful (dates, amounts, states)
3. Be conversational
4. End with ?

EXAMPLES:
- "What is the investor's full legal name?"
- "What amount is being invested? (e.g., $100,000)"

Return ONLY the question."""

        response = model.generate_content(prompt)
        question = response.text.strip().strip('"\'')
        
        if not question.endswith('?'):
            question += '?'
        
        return question
        
    except Exception as e:
        return f"What is the {placeholder['label']}?"

def validate_with_ai(user_input, placeholder, filled_data):
    """Validate user input"""
    if not st.session_state.api_configured:
        return {'valid': True, 'feedback': 'Got it!', 'value': user_input}
    
    try:
        model = genai.GenerativeModel(st.session_state.model_name)
        
        prompt = f"""Validate user input for legal document field.

FIELD: {placeholder['label']}
USER INPUT: "{user_input}"

TASK: Check if reasonable. Respond with JSON only (no markdown):

{{
  "valid": true/false,
  "feedback": "Brief message",
  "value": "cleaned value"
}}

RULES:
- If valid: feedback = "Perfect!" or "Got it!" (1-3 words)
- If invalid: feedback = clarification question (under 15 words)

Return ONLY JSON."""

        response = model.generate_content(prompt)
        ai_text = response.text.strip()
        
        if '```json' in ai_text:
            ai_text = ai_text.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_text:
            ai_text = ai_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(ai_text)
        
        return {
            'valid': result.get('valid', True),
            'feedback': result.get('feedback', 'Recorded'),
            'value': result.get('value', user_input)
        }
        
    except:
        return {'valid': True, 'feedback': 'Recorded', 'value': user_input}

def generate_completed_document():
    """Generate final document"""
    completed = st.session_state.document_text
    for p in st.session_state.placeholders:
        value = st.session_state.filled_data.get(p['key'], p['original'])
        completed = completed.replace(p['original'], value)
    return completed

def reset_app():
    """Reset all state"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Check API
if not GEMINI_API_KEY:
    st.error("⚠️ No API key found! Add GEMINI_API_KEY to .env file")
    st.info("Get free key: https://makersuite.google.com/app/apikey")
    st.stop()

# Header
col1, col2 = st.columns([6, 1])
with col1:
    st.title("📄 Legal Document Processor")
    st.caption("AI-powered document completion")
with col2:
    if st.session_state.step != 'upload':
        if st.button("🔄 Reset"):
            reset_app()

# UPLOAD
if st.session_state.step == 'upload':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="upload-section">
            <h2>📤 Upload Document</h2>
            <p>AI will identify all placeholders</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader("Choose file", type=['txt', 'docx'])
        
        if uploaded_file:
            with st.spinner("🤖 Analyzing..."):
                if uploaded_file.name.endswith('.docx'):
                    text = parse_docx(uploaded_file)
                else:
                    text = uploaded_file.read().decode('utf-8')
                
                if text:
                    st.session_state.document_text = text
                    st.session_state.file_name = uploaded_file.name
                    
                    placeholders = detect_placeholders_with_ai(text)
                    
                    if placeholders:
                        st.session_state.placeholders = placeholders
                        first_q = get_ai_question(placeholders[0], {})
                        
                        st.session_state.messages = [{
                            'type': 'assistant',
                            'content': f"Found {len(placeholders)} fields!\n\n{first_q}"
                        }]
                        st.session_state.step = 'chat'
                        st.rerun()
                    else:
                        st.error("No placeholders detected")

# CHAT
elif st.session_state.step == 'chat':
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 💬 Fill Details")
        
        progress = st.session_state.current_index / len(st.session_state.placeholders)
        st.progress(progress)
        st.caption(f"{st.session_state.current_index}/{len(st.session_state.placeholders)} done")
        st.markdown("---")
        
        # Messages
        for msg in st.session_state.messages:
            if msg['type'] == 'user':
                st.markdown(f'<div class="chat-message user-message"><strong>You:</strong> {msg["content"]}</div>', 
                          unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-message assistant-message"><strong>AI:</strong> {msg["content"]}</div>', 
                          unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Input
        if st.session_state.current_index < len(st.session_state.placeholders):
            with st.form(key='chat', clear_on_submit=True):
                user_input = st.text_input("Answer:", placeholder="Type here...")
                submitted = st.form_submit_button("Send")
                
                if submitted and user_input.strip():
                    st.session_state.messages.append({
                        'type': 'user',
                        'content': user_input.strip()
                    })
                    
                    current = st.session_state.placeholders[st.session_state.current_index]
                    
                    with st.spinner("Validating..."):
                        val = validate_with_ai(user_input.strip(), current, st.session_state.filled_data)
                    
                    if val['valid']:
                        st.session_state.filled_data[current['key']] = val['value']
                        st.session_state.current_index += 1
                        
                        if st.session_state.current_index >= len(st.session_state.placeholders):
                            st.session_state.messages.append({
                                'type': 'assistant',
                                'content': f"{val['feedback']} All done! 🎉"
                            })
                            st.session_state.step = 'complete'
                        else:
                            next_p = st.session_state.placeholders[st.session_state.current_index]
                            next_q = get_ai_question(next_p, st.session_state.filled_data)
                            
                            st.session_state.messages.append({
                                'type': 'assistant',
                                'content': f"{val['feedback']}\n\n{next_q}"
                            })
                    else:
                        st.session_state.messages.append({
                            'type': 'assistant',
                            'content': val['feedback']
                        })
                    
                    st.rerun()
    
    with col2:
        st.markdown("### 📋 Fields")
        
        for idx, p in enumerate(st.session_state.placeholders):
            if idx < st.session_state.current_index:
                status = "completed"
                icon = "✅"
                value = st.session_state.filled_data.get(p['key'], '')
                display = f"<br><small><i>{value}</i></small>"
            elif idx == st.session_state.current_index:
                status = "current"
                icon = "▶️"
                display = ""
            else:
                status = "pending"
                icon = "⭕"
                display = ""
            
            st.markdown(f'<div class="placeholder-box {status}">{icon} <strong>{p["label"]}</strong>{display}</div>', 
                       unsafe_allow_html=True)

# COMPLETE
elif st.session_state.step == 'complete':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="success-box">
            <h1>✅ Complete!</h1>
            <p>Your document is ready</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.spinner("Generating..."):
        if not st.session_state.completed_doc:
            st.session_state.completed_doc = generate_completed_document()
    
    st.markdown("### 📄 Preview")
    st.markdown(f'<div class="doc-preview">{st.session_state.completed_doc}</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.download_button(
            "📥 Download TXT",
            data=st.session_state.completed_doc,
            file_name=f"completed_{st.session_state.file_name.replace('.docx', '.txt')}",
            mime="text/plain"
        )
    
    with col2:
        doc = Document()
        for line in st.session_state.completed_doc.split('\n'):
            doc.add_paragraph(line)
        bio = io.BytesIO()
        doc.save(bio)
        
        st.download_button(
            "📥 Download DOCX",
            data=bio.getvalue(),
            file_name=f"completed_{st.session_state.file_name}",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    
    with col3:
        if st.button("🔄 New"):
            reset_app()

# Sidebar
with st.sidebar:
    st.markdown("### 🤖 AI Status")
    if st.session_state.api_configured and st.session_state.model_name:
        st.success(f"✅ {st.session_state.model_name}")
    else:
        st.error("❌ Not Connected")
    
    st.markdown("---")
    
    if st.session_state.placeholders:
        st.markdown("### 📊 Progress")
        st.metric("Total", len(st.session_state.placeholders))
        st.metric("Done", len(st.session_state.filled_data))
        st.metric("Left", len(st.session_state.placeholders) - len(st.session_state.filled_data))
    
    st.markdown("---")
    st.info("AI-powered with Google Gemini")
