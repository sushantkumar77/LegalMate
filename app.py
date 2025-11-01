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

# Initialize session state
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

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

if GEMINI_API_KEY and not st.session_state.api_configured:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        st.session_state.api_configured = True
    except Exception as e:
        st.error(f"Failed to configure Gemini API: {str(e)}")

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
    """Use Gemini AI to intelligently detect placeholders in document"""
    if not st.session_state.api_configured:
        st.error("❌ Gemini API not configured. Please add GEMINI_API_KEY to .env file.")
        return []
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""You are analyzing a legal document to find ALL placeholders that need user input.

DOCUMENT TEXT:
{text}

TASK: Find every placeholder in the document. Look for:
1. Text in brackets: [Company Name], {{Investor}}, <Date>
2. Underscores or blanks that need filling: _________, _____________
3. Dollar signs with brackets: ${{Amount}}
4. Words like "INSERT", "FILL IN", "[TBD]"

CRITICAL RULES:
- Ignore short underscores (less than 5 characters)
- Each placeholder must be unique and meaningful
- Order them by appearance in document
- Extract clear, descriptive labels

OUTPUT FORMAT (JSON only, no markdown):
{{
  "placeholders": [
    {{
      "label": "Company Name",
      "original": "[Company Name]",
      "description": "The legal name of the company",
      "position": 145
    }}
  ]
}}

Return ONLY valid JSON, no explanations or markdown."""

        response = model.generate_content(prompt)
        ai_text = response.text.strip()
        
        # Clean JSON response
        if '```json' in ai_text:
            ai_text = ai_text.split('```json')[1].split('```')[0].strip()
        elif '```' in ai_text:
            ai_text = ai_text.split('```')[1].split('```')[0].strip()
        
        result = json.loads(ai_text)
        
        placeholders = []
        seen_labels = set()
        
        for item in result.get('placeholders', []):
            label = item['label'].strip()
            
            # Skip if we've seen this label or if it's too generic
            if label in seen_labels or label.lower() in ['the', 'and', 'or', 'insert']:
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
    """Generate smart, context-aware question for placeholder"""
    if not st.session_state.api_configured:
        return f"What should I use for {placeholder['label']}?"
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Get document context around placeholder
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
        
        prompt = f"""Generate ONE clear question to ask the user for this information.

PLACEHOLDER: {placeholder['label']}
APPEARS AS: {placeholder['original']}
DESCRIPTION: {placeholder.get('description', 'N/A')}

DOCUMENT CONTEXT:
...{context}...

ALREADY FILLED:
{filled_info}

REQUIREMENTS:
1. Ask ONE specific question (under 20 words)
2. Include helpful examples if applicable (dates, amounts, states)
3. Be conversational and clear
4. Do NOT repeat information from previous questions
5. End with a question mark

EXAMPLES:
- "What is the investor's full legal name?"
- "What amount is being invested? (e.g., $100,000)"
- "What date is this agreement signed? (format: January 15, 2024)"

Return ONLY the question, nothing else."""

        response = model.generate_content(prompt)
        question = response.text.strip().strip('"\'')
        
        if not question.endswith('?'):
            question += '?'
        
        return question
        
    except Exception as e:
        return f"What is the {placeholder['label']}?"

def validate_with_ai(user_input, placeholder, filled_data):
    """Validate user input and determine if we should proceed or ask for clarification"""
    if not st.session_state.api_configured:
        return {
            'valid': True,
            'feedback': f"Got it: {user_input}",
            'value': user_input
        }
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""You are validating user input for a legal document.

FIELD: {placeholder['label']}
USER'S ANSWER: "{user_input}"

ALREADY FILLED:
{chr(10).join([f"- {k}: {v}" for k, v in filled_data.items()]) if filled_data else "None yet"}

TASK:
1. Check if "{user_input}" is reasonable for field "{placeholder['label']}"
2. Respond with JSON only (no markdown)

OUTPUT FORMAT:
{{
  "valid": true/false,
  "feedback": "Brief confirmation or request for clarification",
  "value": "cleaned/formatted value"
}}

RULES:
- If valid: feedback should be 1-2 words like "Perfect!" or "Got it!"
- If invalid: feedback should ask for clarification (under 15 words)
- Always be professional and concise

Return ONLY valid JSON."""

        response = model.generate_content(prompt)
        ai_text = response.text.strip()
        
        # Clean JSON
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
        
    except Exception as e:
        return {
            'valid': True,
            'feedback': 'Recorded',
            'value': user_input
        }

def generate_completed_document():
    """Generate final document with all placeholders filled"""
    if not st.session_state.api_configured:
        # Simple replacement
        completed = st.session_state.document_text
        for p in st.session_state.placeholders:
            value = st.session_state.filled_data.get(p['key'], p['original'])
            completed = completed.replace(p['original'], value)
        return completed
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        replacements = []
        for p in st.session_state.placeholders:
            value = st.session_state.filled_data.get(p['key'], p['original'])
            replacements.append(f"Replace '{p['original']}' with '{value}'")
        
        prompt = f"""Replace placeholders in this document with provided values. Maintain exact formatting.

ORIGINAL DOCUMENT:
{st.session_state.document_text}

REPLACEMENTS:
{chr(10).join(replacements)}

Return ONLY the completed document. No explanations, no markdown formatting."""

        response = model.generate_content(prompt)
        completed = response.text.strip()
        
        # Remove markdown if AI added it
        if '```' in completed:
            parts = completed.split('```')
            if len(parts) >= 2:
                completed = parts[1]
                if '\n' in completed:
                    lines = completed.split('\n')
                    completed = '\n'.join(lines[1:]) if lines[0].strip() in ['text', 'plaintext', ''] else '\n'.join(lines)
        
        return completed.strip()
        
    except Exception as e:
        st.warning(f"AI generation failed: {str(e)}")
        # Fallback to simple replacement
        completed = st.session_state.document_text
        for p in st.session_state.placeholders:
            value = st.session_state.filled_data.get(p['key'], p['original'])
            completed = completed.replace(p['original'], value)
        return completed

def reset_app():
    """Reset all session state"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Check API configuration
if not GEMINI_API_KEY:
    st.error("⚠️ Gemini API Key not found! Add GEMINI_API_KEY to your .env file")
    st.info("Get your free API key: https://makersuite.google.com/app/apikey")
    st.stop()

# Header
col1, col2 = st.columns([6, 1])
with col1:
    st.title("📄 Legal Document Processor")
    st.caption("AI-powered document completion with intelligent placeholder detection")
with col2:
    if st.session_state.step != 'upload':
        if st.button("🔄 Reset"):
            reset_app()

# UPLOAD STEP
if st.session_state.step == 'upload':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="upload-section">
            <h2>📤 Upload Your Document</h2>
            <p>Upload a legal document and AI will identify all placeholders</p>
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['txt', 'docx'],
            help="Supports .txt and .docx files"
        )
        
        if uploaded_file:
            with st.spinner("🤖 Analyzing document with AI..."):
                # Parse file
                if uploaded_file.name.endswith('.docx'):
                    text = parse_docx(uploaded_file)
                else:
                    text = uploaded_file.read().decode('utf-8')
                
                if text:
                    st.session_state.document_text = text
                    st.session_state.file_name = uploaded_file.name
                    
                    # Detect placeholders with AI
                    placeholders = detect_placeholders_with_ai(text)
                    
                    if placeholders:
                        st.session_state.placeholders = placeholders
                        
                        # Generate first question
                        first_question = get_ai_question(placeholders[0], {})
                        
                        st.session_state.messages = [{
                            'type': 'assistant',
                            'content': f"I found {len(placeholders)} fields to fill. Let's start!\n\n{first_question}"
                        }]
                        st.session_state.step = 'chat'
                        st.rerun()
                    else:
                        st.error("No placeholders found in your document.")

# CHAT STEP
elif st.session_state.step == 'chat':
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 💬 Fill in the Details")
        
        # Progress
        progress = st.session_state.current_index / len(st.session_state.placeholders)
        st.progress(progress)
        st.caption(f"{st.session_state.current_index}/{len(st.session_state.placeholders)} completed")
        st.markdown("---")
        
        # Chat history
        for msg in st.session_state.messages:
            if msg['type'] == 'user':
                st.markdown(f'<div class="chat-message user-message"><strong>You:</strong> {msg["content"]}</div>', 
                          unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-message assistant-message"><strong>AI:</strong> {msg["content"]}</div>', 
                          unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Input form
        if st.session_state.current_index < len(st.session_state.placeholders):
            with st.form(key='chat_form', clear_on_submit=True):
                user_input = st.text_input("Your answer:", placeholder="Type here...")
                submitted = st.form_submit_button("Send")
                
                if submitted and user_input.strip():
                    # Add user message
                    st.session_state.messages.append({
                        'type': 'user',
                        'content': user_input.strip()
                    })
                    
                    current_placeholder = st.session_state.placeholders[st.session_state.current_index]
                    
                    # Validate with AI
                    with st.spinner("Validating..."):
                        validation = validate_with_ai(user_input.strip(), current_placeholder, st.session_state.filled_data)
                    
                    if validation['valid']:
                        # Save value and move to next
                        st.session_state.filled_data[current_placeholder['key']] = validation['value']
                        st.session_state.current_index += 1
                        st.session_state.waiting_for_clarification = False
                        
                        # Check if done
                        if st.session_state.current_index >= len(st.session_state.placeholders):
                            st.session_state.messages.append({
                                'type': 'assistant',
                                'content': f"{validation['feedback']} All done! 🎉"
                            })
                            st.session_state.step = 'complete'
                        else:
                            # Ask next question
                            next_placeholder = st.session_state.placeholders[st.session_state.current_index]
                            next_question = get_ai_question(next_placeholder, st.session_state.filled_data)
                            
                            st.session_state.messages.append({
                                'type': 'assistant',
                                'content': f"{validation['feedback']}\n\n{next_question}"
                            })
                    else:
                        # Need clarification
                        st.session_state.waiting_for_clarification = True
                        st.session_state.messages.append({
                            'type': 'assistant',
                            'content': validation['feedback']
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

# COMPLETE STEP
elif st.session_state.step == 'complete':
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="success-box">
            <h1>✅ Document Complete!</h1>
            <p>Your document is ready for review and download</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Generate final document
    with st.spinner("Generating final document..."):
        if not st.session_state.completed_doc:
            st.session_state.completed_doc = generate_completed_document()
    
    # Preview
    st.markdown("### 📄 Preview")
    st.markdown(f'<div class="doc-preview">{st.session_state.completed_doc}</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Download buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.download_button(
            "📥 Download TXT",
            data=st.session_state.completed_doc,
            file_name=f"completed_{st.session_state.file_name.replace('.docx', '.txt')}",
            mime="text/plain"
        )
    
    with col2:
        # Generate DOCX
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
        if st.button("🔄 New Document"):
            reset_app()

# Sidebar
with st.sidebar:
    st.markdown("### 🤖 AI Status")
    if st.session_state.api_configured:
        st.success("✅ Gemini Connected")
    else:
        st.error("❌ Not Connected")
    
    st.markdown("---")
    
    if st.session_state.placeholders:
        st.markdown("### 📊 Progress")
        st.metric("Total Fields", len(st.session_state.placeholders))
        st.metric("Completed", len(st.session_state.filled_data))
        st.metric("Remaining", len(st.session_state.placeholders) - len(st.session_state.filled_data))
    
    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.info("AI-powered document processor using Google Gemini")
    st.caption("Secure • Fast • Intelligent")
