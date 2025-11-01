import streamlit as st
import re
import io
import google.generativeai as genai
from docx import Document
import os
from datetime import datetime

st.set_page_config(
    page_title="Legal Document Processor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main {
        padding: 0rem 1rem;
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        font-weight: 600;
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
        background-color: #f1f3f4;
        color: black;
        margin-right: 20%;
    }
    .placeholder-box {
        padding: 0.8rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        border-left: 4px solid;
    }
    .completed {
        background-color: #d4edda;
        border-color: #28a745;
    }
    .current {
        background-color: #cce5ff;
        border-color: #007bff;
    }
    .pending {
        background-color: #f8f9fa;
        border-color: #dee2e6;
    }
    .success-box {
        padding: 1.5rem;
        border-radius: 10px;
        background-color: #d4edda;
        border: 2px solid #28a745;
        text-align: center;
    }
    .doc-preview {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        max-height: 500px;
        overflow-y: auto;
        font-family: monospace;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)

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

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')

def detect_placeholders(text):
    patterns = [
        (r'\[([^\]]+)\]', 'square'),
        (r'\{([^}]+)\}', 'curly'),
        (r'\$\{([^}]+)\}', 'dollar'),
        (r'<([^>]+)>', 'angle'),
        (r'\[\[([^\]]+)\]\]', 'double-square'),
        (r'\{\{([^}]+)\}\}', 'double-curly'),
        (r'_{3,}', 'underscore'),
        (r'\.{3,}', 'dots'),
    ]
    
    found = {}
    locations = []
    
    for pattern, pattern_type in patterns:
        for match in re.finditer(pattern, text):
            if match.groups():
                placeholder = match.group(1).strip()
            else:
                placeholder = match.group(0).strip()
            
            if len(placeholder) < 2 or len(placeholder) > 100:
                continue
            if placeholder.upper() in ['THE', 'AND', 'OR', 'OF', 'IN', 'TO', 'A', 'IS', 'IT', 'AT']:
                continue
            
            key = re.sub(r'[^a-z0-9]', '_', placeholder.lower())
            
            if key not in found:
                found[key] = True
                locations.append({
                    'key': key,
                    'label': placeholder,
                    'original': match.group(0),
                    'value': '',
                    'position': match.start(),
                    'type': pattern_type
                })
    
    return sorted(locations, key=lambda x: x['position'])

def parse_docx(file):
    try:
        doc = Document(file)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        st.error(f"Error parsing DOCX: {str(e)}")
        return ""

def get_ai_response(user_message, current_placeholder, filled_data):
    if not GEMINI_API_KEY:
        return {
            'response': f"Got it! I've recorded '{user_message}' for {current_placeholder['label']}.",
            'should_proceed': True,
            'validated_value': user_message
        }
    
    try:
        prompt = f"""You are an AI assistant helping to fill out a legal document.

Current placeholder to fill: "{current_placeholder['label']}"
User's response: "{user_message}"

Your tasks:
1. Validate if the user's response is appropriate for "{current_placeholder['label']}"
2. If valid, acknowledge briefly (1 sentence) and confirm you're ready for the next field
3. If invalid or incomplete, ask for clarification politely
4. Be professional, concise, and helpful

Already filled placeholders:
{chr(10).join([f"- {k}: {v}" for k, v in filled_data.items()])}

Respond in a conversational, professional tone. Keep response under 50 words."""

        response = model.generate_content(prompt)
        ai_text = response.text
        
        should_proceed = not any(word in ai_text.lower() for word in 
                                ['clarify', 'invalid', 'please provide', 'could you', 'can you provide'])
        
        return {
            'response': ai_text,
            'should_proceed': should_proceed,
            'validated_value': user_message if should_proceed else None
        }
    except Exception as e:
        st.error(f"AI Error: {str(e)}")
        return {
            'response': f"Recorded: {user_message}",
            'should_proceed': True,
            'validated_value': user_message
        }

def generate_completed_document():
    completed = st.session_state.document_text
    for placeholder in st.session_state.placeholders:
        value = st.session_state.filled_data.get(placeholder['key'], placeholder['original'])
        completed = completed.replace(placeholder['original'], value)
    return completed

def reset_app():
    st.session_state.step = 'upload'
    st.session_state.placeholders = []
    st.session_state.filled_data = {}
    st.session_state.messages = []
    st.session_state.current_index = 0
    st.session_state.document_text = ""
    st.session_state.file_name = ""
    st.session_state.completed_doc = ""
    st.rerun()

col1, col2 = st.columns([6, 1])
with col1:
    st.title("📄 Legal Document Processor")
    st.caption("AI-powered document completion with intelligent placeholder detection")
with col2:
    if st.session_state.step != 'upload':
        if st.button("🔄 Reset", use_container_width=True):
            reset_app()

if st.session_state.step == 'upload':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="upload-section">
            <h2>📤 Upload Your Document</h2>
            <p>Upload a legal document with placeholders and I'll help you fill them in</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['txt', 'docx'],
            help="Supports .txt and .docx files up to 10MB"
        )
        
        if uploaded_file:
            with st.spinner("Processing document..."):
                if uploaded_file.name.endswith('.docx'):
                    text = parse_docx(uploaded_file)
                else:
                    text = uploaded_file.read().decode('utf-8')
                
                if text:
                    st.session_state.document_text = text
                    st.session_state.file_name = uploaded_file.name
                    
                    placeholders = detect_placeholders(text)
                    
                    if placeholders:
                        st.session_state.placeholders = placeholders
                        st.session_state.messages = [{
                            'type': 'assistant',
                            'content': f"I've analyzed your document and found {len(placeholders)} placeholders to fill. Let's start! What is the {placeholders[0]['label']}?",
                            'timestamp': datetime.now()
                        }]
                        st.session_state.step = 'chat'
                        st.rerun()
                    else:
                        st.error("❌ No placeholders detected in your document. Please upload a document with placeholders like [Company Name], {Date}, etc.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.expander("ℹ️ Supported Placeholder Formats"):
            st.markdown("""
            - [Company Name] - Square brackets
            - {Date} - Curly braces  
            - <Amount> - Angle brackets
            - ${Variable} - Dollar sign with braces
            - [[Field]] - Double square brackets
            - {{Field}} - Double curly braces
            - _____ - Underscores (3 or more)
            - ... - Dots (3 or more)
            """)

elif st.session_state.step == 'chat':
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 💬 Fill in the Details")
        
        progress = st.session_state.current_index / len(st.session_state.placeholders)
        st.progress(progress)
        st.caption(f"Progress: {st.session_state.current_index} of {len(st.session_state.placeholders)} completed")
        
        st.markdown("---")
        
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.messages:
                if msg['type'] == 'user':
                    st.markdown(f"""
                    <div class="chat-message user-message">
                        <strong>You:</strong> {msg['content']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>Assistant:</strong> {msg['content']}
                    </div>
                    """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        if st.session_state.current_index < len(st.session_state.placeholders):
            with st.form(key='chat_form', clear_on_submit=True):
                user_input = st.text_input(
                    "Your answer:",
                    placeholder="Type your response here...",
                    key='user_input'
                )
                submit = st.form_submit_button("Send", use_container_width=True)
                
                if submit and user_input:
                    st.session_state.messages.append({
                        'type': 'user',
                        'content': user_input,
                        'timestamp': datetime.now()
                    })
                    
                    current_placeholder = st.session_state.placeholders[st.session_state.current_index]
                    ai_result = get_ai_response(user_input, current_placeholder, st.session_state.filled_data)
                    
                    if ai_result['should_proceed']:
                        st.session_state.filled_data[current_placeholder['key']] = user_input
                        st.session_state.current_index += 1
                        
                        if st.session_state.current_index < len(st.session_state.placeholders):
                            next_placeholder = st.session_state.placeholders[st.session_state.current_index]
                            response = f"{ai_result['response']} Next: What is the {next_placeholder['label']}?"
                        else:
                            response = "Perfect! All placeholders have been filled. Your document is ready for review! 🎉"
                            st.session_state.step = 'complete'
                    else:
                        response = ai_result['response']
                    
                    st.session_state.messages.append({
                        'type': 'assistant',
                        'content': response,
                        'timestamp': datetime.now()
                    })
                    
                    st.rerun()
    
    with col2:
        st.markdown("### 📋 Placeholders")
        
        for idx, placeholder in enumerate(st.session_state.placeholders):
            if idx < st.session_state.current_index:
                status_class = "completed"
                icon = "✅"
            elif idx == st.session_state.current_index:
                status_class = "current"
                icon = "▶️"
            else:
                status_class = "pending"
                icon = "⭕"
            
            value_text = st.session_state.filled_data.get(placeholder['key'], '')
            value_display = f"<br><small><i>{value_text}</i></small>" if value_text else ""
            
            st.markdown(f"""
            <div class="placeholder-box {status_class}">
                {icon} <strong>{placeholder['label']}</strong>{value_display}
            </div>
            """, unsafe_allow_html=True)

elif st.session_state.step == 'complete':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="success-box">
            <h1>✅ Document Complete!</h1>
            <p>All placeholders have been filled. Review and download your document.</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    completed_doc = generate_completed_document()
    st.session_state.completed_doc = completed_doc
    
    st.markdown("### 📄 Document Preview")
    st.markdown(f'<div class="doc-preview">{completed_doc}</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.download_button(
            label="📥 Download as TXT",
            data=completed_doc,
            file_name=f"completed_{st.session_state.file_name.replace('.docx', '.txt')}",
            mime="text/plain",
            use_container_width=True
        )
    
    with col2:
        doc = Document()
        for line in completed_doc.split('\n'):
            doc.add_paragraph(line)
        
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        
        st.download_button(
            label="📥 Download as DOCX",
            data=bio.getvalue(),
            file_name=f"completed_{st.session_state.file_name}",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
    
    with col3:
        if st.button("🔄 Process Another", use_container_width=True):
            reset_app()

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    
    api_key_input = st.text_input(
        "Gemini API Key",
        value=GEMINI_API_KEY,
        type="password",
        help="Enter your Google Gemini API key for AI-powered responses"
    )
    
    if api_key_input and api_key_input != GEMINI_API_KEY:
        os.environ['GEMINI_API_KEY'] = api_key_input
        genai.configure(api_key=api_key_input)
        st.success("✅ API Key updated!")
    
    st.markdown("---")
    
    st.markdown("### 📊 Statistics")
    if st.session_state.placeholders:
        st.metric("Total Placeholders", len(st.session_state.placeholders))
        st.metric("Filled", len(st.session_state.filled_data))
        st.metric("Remaining", len(st.session_state.placeholders) - len(st.session_state.filled_data))
    
    st.markdown("---")
    
    st.markdown("### ℹ️ About")
    st.info("""
    This app helps you fill legal documents by:
    - Detecting placeholders automatically
    - Guiding you through each field
    - Using AI to validate inputs
    - Generating completed documents
    """)
    
    st.markdown("---")
    st.caption("Built with Streamlit & Google Gemini AI")
