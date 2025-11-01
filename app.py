import streamlit as st
import re
from docx import Document
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Document Placeholder Filler", page_icon="📝", layout="wide")

def extract_text_and_placeholders(docx_file):
    try:
        doc = Document(docx_file)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text.append(cell.text)
        text = "\n".join(full_text)
        
        # More precise patterns that avoid matching formatting or empty brackets
        patterns = [
            r'\{\{([^}]+)\}\}',  # {{placeholder}}
            r'\{([^{}]+)\}',      # {placeholder} - avoid nested braces
            r'\[([^\[\]]+)\]',    # [placeholder] - avoid nested brackets
            r'<<([^<>]+)>>',      # <<placeholder>>
        ]
        
        placeholders = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            placeholders.update(matches)
        
        # Create a mapping to track what each placeholder should become
        placeholder_mapping = {}
        
        # Improved filtering to remove invalid placeholders
        filtered_placeholders = []
        for p in placeholders:
            p_clean = p.strip()
            
            # Skip if empty or too short
            if len(p_clean) < 1:
                continue
            
            # Special handling for underscores-only placeholders like [_____________]
            # These represent blank fill-in fields
            if all(c in ['_', '-', ' '] for c in p_clean):
                # Count how many underscores and create a descriptive name
                underscore_count = p_clean.count('_')
                if underscore_count >= 3:  # Only if there are multiple underscores
                    # Try to infer context from surrounding text
                    # For now, create a generic placeholder name
                    context_name = f"blank_field_{len(filtered_placeholders) + 1}"
                    placeholder_mapping[p] = context_name
                    filtered_placeholders.append(p)  # Keep original for replacement
                continue
            
            # Skip if it's just numbers
            if p_clean.isdigit():
                continue
            
            # Skip if it looks like formatting (e.g., "underline", "bold")
            formatting_keywords = ['underline', 'bold', 'italic', 'excluding', 'other than']
            if p_clean.lower() in formatting_keywords:
                continue
            
            # Check if it has at least some alphanumeric content
            has_alnum = any(c.isalnum() for c in p_clean)
            if not has_alnum and not all(c in ['_', '-', ' '] for c in p_clean):
                continue
            
            filtered_placeholders.append(p_clean)
        
        # Store mapping for later use
        if not hasattr(st.session_state, 'placeholder_mapping'):
            st.session_state.placeholder_mapping = placeholder_mapping
        
        return text, sorted(list(set(filtered_placeholders)))
    except Exception as e:
        st.error(f"Error reading document: {str(e)}")
        return "", []

def generate_question_from_placeholder(placeholder, use_llm=False, api_key=None):
    # Check if this is an underscore-only placeholder
    if all(c in ['_', '-', ' '] for c in placeholder.strip()):
        # Try to infer context from document position
        # For now, ask a generic question
        return "Please provide the value for this field:"
    
    # Dictionary of better question phrasings for common placeholders
    better_questions = {
        'Investor Name': 'What is the investor\'s full name?',
        'investor name': 'What is the investor\'s full name?',
        'Company Name': 'What is the company\'s full legal name?',
        'company name': 'What is the company\'s full legal name?',
        'State of Incorporation': 'In which U.S. state is the company incorporated? (e.g., Delaware, California)',
        'state of incorporation': 'In which U.S. state is the company incorporated? (e.g., Delaware, California)',
        'Governing Law Jurisdiction': 'Which U.S. state law will govern this agreement? (e.g., Delaware, California)',
        'governing law jurisdiction': 'Which U.S. state law will govern this agreement? (e.g., Delaware, California)',
        'name': 'What is the person\'s full name?',
        'title': 'What is the person\'s job title?',
    }
    
    # Check if we have a custom question for this placeholder
    if placeholder in better_questions:
        return better_questions[placeholder]
    
    # Check for variations (case-insensitive)
    for key, question in better_questions.items():
        if placeholder.lower() == key.lower():
            return question
    
    # Otherwise, generate a question using smart logic
    readable = placeholder.replace('_', ' ').replace('-', ' ')
    readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable)
    readable = ' '.join(readable.split())
    
    # Special handling for common patterns
    lower_readable = readable.lower()
    
    # Check for specific terms and provide context
    if 'purchase amount' in lower_readable or 'investment amount' in lower_readable:
        return f"What is the investment amount? (Enter amount in USD, e.g., 50000)"
    elif 'valuation cap' in lower_readable or 'post-money' in lower_readable:
        return f"What is the post-money valuation cap? (Enter amount in USD, e.g., 5000000)"
    elif 'date' in lower_readable and 'safe' in lower_readable:
        return "What is the signing date of this SAFE agreement? (e.g., January 15, 2024)"
    elif 'date' in lower_readable:
        return f"What is the {readable}? (e.g., January 15, 2024)"
    elif 'name' in lower_readable:
        return f"What is the {readable}?"
    elif 'amount' in lower_readable or 'price' in lower_readable:
        return f"What is the {readable}? (Enter amount in USD)"
    elif 'email' in lower_readable:
        return f"What is the {readable}? (e.g., user@example.com)"
    elif 'phone' in lower_readable or 'number' in lower_readable:
        return f"What is the {readable}?"
    elif 'address' in lower_readable:
        return f"What is the {readable}?"
    elif 'state' in lower_readable or 'jurisdiction' in lower_readable:
        return f"What is the {readable}? (Enter U.S. state name)"
    else:
        # For other cases, preserve capitalization
        if readable.islower():
            readable = readable.capitalize()
        elif readable.isupper():
            readable = readable.title()
        return f"What is the {readable}?"

def replace_placeholders_in_docx(original_file, placeholder_values):
    try:
        original_file.seek(0)
        doc = Document(original_file)
        for para in doc.paragraphs:
            for placeholder, value in placeholder_values.items():
                patterns = [
                    (f'{{{{{placeholder}}}}}', value),
                    (f'{{{placeholder}}}', value),
                    (f'[{placeholder}]', value),
                    (f'<<{placeholder}>>', value),
                ]
                for pattern, replacement in patterns:
                    if pattern in para.text:
                        for run in para.runs:
                            if pattern in run.text:
                                run.text = run.text.replace(pattern, replacement)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for placeholder, value in placeholder_values.items():
                        patterns = [
                            (f'{{{{{placeholder}}}}}', value),
                            (f'{{{placeholder}}}', value),
                            (f'[{placeholder}]', value),
                            (f'<<{placeholder}>>', value),
                        ]
                        for pattern, replacement in patterns:
                            if pattern in cell.text:
                                for para in cell.paragraphs:
                                    for run in para.runs:
                                        if pattern in run.text:
                                            run.text = run.text.replace(pattern, replacement)
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Error replacing placeholders: {str(e)}")
        return None

if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None
if 'placeholders' not in st.session_state:
    st.session_state.placeholders = []
if 'current_placeholder_index' not in st.session_state:
    st.session_state.current_placeholder_index = 0
if 'placeholder_values' not in st.session_state:
    st.session_state.placeholder_values = {}
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'document_completed' not in st.session_state:
    st.session_state.document_completed = False
if 'original_file_bytes' not in st.session_state:
    st.session_state.original_file_bytes = None

st.title("📝 Document Placeholder Filler")
st.markdown("Upload a .docx document with placeholders, and I'll help you fill them in through a conversational interface!")

with st.sidebar:
    st.header("⚙️ Settings")
    use_llm = st.checkbox("Use Gemini API for Questions", value=False, help="Generate more natural questions using AI")
    gemini_api_key = None
    if use_llm:
        gemini_api_key = st.text_input("Gemini API Key", type="password", help="Enter your Google Gemini API key")
    st.markdown("---")
    st.header("ℹ️ How it works")
    st.markdown("""
    1. Upload a `.docx` file with placeholders
    2. Supported formats:
       - `{{placeholder}}`
       - `{placeholder}`
       - `[placeholder]`
       - `<<placeholder>>`
    3. Answer questions in the chat
    4. Download your completed document
    """)
    st.markdown("---")
    if st.button("🔄 Start Over", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

if not st.session_state.document_completed:
    uploaded_file = st.file_uploader("Upload your .docx document", type=['docx'], help="Upload a Word document containing placeholders to fill")
    if uploaded_file is not None:
        if st.session_state.uploaded_file is None or uploaded_file.name != st.session_state.uploaded_file:
            st.session_state.uploaded_file = uploaded_file.name
            st.session_state.original_file_bytes = uploaded_file.getvalue()
            file_bytes = BytesIO(st.session_state.original_file_bytes)
            text, placeholders = extract_text_and_placeholders(file_bytes)
            if placeholders:
                st.session_state.placeholders = placeholders
                st.session_state.current_placeholder_index = 0
                st.session_state.placeholder_values = {}
                st.session_state.chat_history = []
                st.session_state.document_completed = False
                st.success(f"✅ Document uploaded! Found {len(placeholders)} placeholders to fill.")
                with st.expander("📋 Detected Placeholders"):
                    for i, placeholder in enumerate(placeholders, 1):
                        st.write(f"{i}. `{placeholder}`")
            else:
                st.warning("⚠️ No placeholders detected in the document. Please ensure your document contains placeholders in supported formats.")
                st.session_state.uploaded_file = None

if st.session_state.placeholders and not st.session_state.document_completed:
    st.markdown("---")
    st.header("💬 Fill in the Placeholders")
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            if message['role'] == 'assistant':
                with st.chat_message("assistant"):
                    st.write(message['content'])
            else:
                with st.chat_message("user"):
                    st.write(message['content'])
    if st.session_state.current_placeholder_index < len(st.session_state.placeholders):
        current_placeholder = st.session_state.placeholders[st.session_state.current_placeholder_index]
        if not st.session_state.chat_history or st.session_state.chat_history[-1]['role'] != 'assistant':
            question = generate_question_from_placeholder(current_placeholder, use_llm=use_llm, api_key=gemini_api_key if use_llm else None)
            st.session_state.chat_history.append({
                'role': 'assistant',
                'content': f"**Question {st.session_state.current_placeholder_index + 1}/{len(st.session_state.placeholders)}:** {question}"
            })
            st.rerun()
        user_input = st.chat_input(f"Enter value for '{current_placeholder}'...")
        if user_input:
            st.session_state.placeholder_values[current_placeholder] = user_input
            st.session_state.chat_history.append({'role': 'user', 'content': user_input})
            st.session_state.current_placeholder_index += 1
            if st.session_state.current_placeholder_index >= len(st.session_state.placeholders):
                st.session_state.document_completed = True
                st.session_state.chat_history.append({'role': 'assistant', 'content': "🎉 Great! All placeholders have been filled. You can now download your completed document below."})
            st.rerun()

if st.session_state.document_completed and st.session_state.original_file_bytes:
    st.markdown("---")
    st.header("✅ Document Complete!")
    original_file = BytesIO(st.session_state.original_file_bytes)
    completed_doc = replace_placeholders_in_docx(original_file, st.session_state.placeholder_values)
    if completed_doc:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📄 Filled Values")
            for placeholder, value in st.session_state.placeholder_values.items():
                st.write(f"**{placeholder}:** {value}")
        with col2:
            st.subheader("⬇️ Download Options")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            docx_filename = f"completed_document_{timestamp}.docx"
            st.download_button(
                label="📥 Download as DOCX",
                data=completed_doc.getvalue(),
                file_name=docx_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            st.info("💡 To convert to PDF, download the DOCX file and use Microsoft Word, Google Docs, or an online converter.")
        st.markdown("---")
        if st.button("✏️ Edit Values", use_container_width=True):
            st.session_state.document_completed = False
            st.session_state.current_placeholder_index = 0
            st.session_state.chat_history = []
            st.rerun()

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em;'>
    Made By Sushant Kumar using Streamlit | Supports .docx files with multiple placeholder formats
    </div>
    """,
    unsafe_allow_html=True
)
