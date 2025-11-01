import streamlit as st
import re
from docx import Document
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Document Placeholder Filler", page_icon="📝", layout="wide")

def extract_text_and_placeholders(docx_file):
    """
    Universal placeholder extraction that works with any document type.
    Detects: {{x}}, {x}, [x], <<x>>, and blank fields like [____]
    """
    try:
        doc = Document(docx_file)
        full_text = []
        
        # Extract all text from paragraphs and tables
        for para in doc.paragraphs:
            full_text.append(para.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text.append(cell.text)
        
        text = "\n".join(full_text)
        
        # Multiple pattern formats to catch all placeholder styles
        patterns = [
            r'\{\{([^}]+)\}\}',      # {{placeholder}}
            r'\{([^{}]+)\}',          # {placeholder}
            r'\[([^\[\]]+)\]',        # [placeholder]
            r'<<([^<>]+)>>',          # <<placeholder>>
        ]
        
        raw_placeholders = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                raw_placeholders.append(match.strip())
        
        # Smart filtering to remove non-placeholders
        filtered_placeholders = []
        seen = set()
        
        for p in raw_placeholders:
            # Skip if already processed
            if p in seen:
                continue
            
            # Skip completely empty
            if len(p) == 0:
                continue
            
            # Handle underscore-only fields (blank fill-ins like [_______])
            if re.match(r'^[_\s\-]+$', p):
                # Only include if it has 3+ underscores (meaningful blank field)
                if p.count('_') >= 3 or p.count('-') >= 3:
                    # Try to find context
                    context = find_context_for_blank(text, p)
                    if context:
                        filtered_placeholders.append(p)
                        seen.add(p)
                continue
            
            # Skip common document formatting artifacts
            skip_words = [
                'underline', 'bold', 'italic', 'strike', 'strikethrough',
                'excluding', 'other than', 'provided', 'including',
                'without limitation', 'e.g.', 'i.e.', 'etc'
            ]
            if p.lower() in skip_words:
                continue
            
            # Skip if it's just punctuation
            if re.match(r'^[^\w\s]+$', p):
                continue
            
            # Skip pure numbers (likely page numbers or references)
            if p.isdigit():
                continue
            
            # Skip very short strings unless they're common abbreviations
            if len(p) == 1:
                continue
            
            # Must contain at least one letter or underscore
            if not re.search(r'[a-zA-Z_]', p):
                continue
            
            # Add to filtered list
            filtered_placeholders.append(p)
            seen.add(p)
        
        # Remove exact duplicates and maintain document order
        return text, filtered_placeholders
        
    except Exception as e:
        st.error(f"Error reading document: {str(e)}")
        return "", []


def find_context_for_blank(text, blank_placeholder):
    """
    Find surrounding text to understand what a blank field represents.
    Returns the inferred field name or None.
    """
    # Escape special regex characters
    escaped = re.escape(f'[{blank_placeholder}]')
    
    # Look for text before the blank (up to 100 characters)
    pattern = r'(.{0,100})' + escaped
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        before_text = match.group(1).lower()
        
        # Common patterns to look for
        if '$' in before_text[-10:]:
            if 'amount' in before_text:
                return 'amount_field'
            elif 'price' in before_text or 'value' in before_text:
                return 'price_field'
            else:
                return 'currency_field'
        
        # Check for date indicators
        if any(word in before_text[-30:] for word in ['date', 'dated', 'day of']):
            return 'date_field'
        
        # Check for name indicators
        if any(word in before_text[-30:] for word in ['name', 'named', 'by and between']):
            return 'name_field'
        
        # Otherwise include if it seems like a meaningful blank
        return 'blank_field'
    
    return None


def generate_question_from_placeholder(placeholder):
    """
    Universal question generator that works for any placeholder.
    Uses pattern matching and common sense to create clear questions.
    """
    
    # Handle blank/underscore placeholders
    if re.match(r'^[_\s\-]+$', placeholder):
        return "Please provide the value for this blank field:"
    
    # Clean up the placeholder for analysis
    readable = placeholder.replace('_', ' ').replace('-', ' ')
    readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', readable)  # camelCase to spaces
    readable = ' '.join(readable.split())  # normalize spaces
    lower_readable = readable.lower()
    
    # Pattern-based question generation with examples
    
    # Money/Currency patterns
    if any(word in lower_readable for word in ['amount', 'price', 'payment', 'fee', 'cost', 'salary', 'wage', 'compensation']):
        return f"What is the {readable}? (e.g., 50000 or $50,000)"
    
    if any(word in lower_readable for word in ['valuation', 'cap', 'value']):
        return f"What is the {readable}? (e.g., 5000000)"
    
    # Date patterns
    if any(word in lower_readable for word in ['date', 'day', 'month', 'year', 'when']):
        return f"What is the {readable}? (e.g., January 15, 2024 or 01/15/2024)"
    
    # Name patterns
    if 'name' in lower_readable:
        if any(word in lower_readable for word in ['company', 'business', 'organization', 'entity']):
            return f"What is the {readable}? (Full legal name)"
        elif any(word in lower_readable for word in ['person', 'individual', 'party', 'client', 'employee', 'investor']):
            return f"What is the {readable}? (Full name)"
        else:
            return f"What is the {readable}?"
    
    # Contact information
    if 'email' in lower_readable or 'e-mail' in lower_readable:
        return f"What is the {readable}? (e.g., user@example.com)"
    
    if 'phone' in lower_readable or 'telephone' in lower_readable or 'mobile' in lower_readable:
        return f"What is the {readable}? (e.g., +1-555-123-4567 or (555) 123-4567)"
    
    if 'address' in lower_readable:
        if 'email' in lower_readable:
            return f"What is the {readable}? (e.g., user@example.com)"
        else:
            return f"What is the {readable}? (Full address including city, state, ZIP)"
    
    if any(word in lower_readable for word in ['zip', 'postal', 'postcode']):
        return f"What is the {readable}? (e.g., 12345 or 12345-6789)"
    
    if 'city' in lower_readable:
        return f"What is the {readable}? (e.g., San Francisco)"
    
    # Location patterns
    if any(word in lower_readable for word in ['state', 'province', 'region']):
        return f"What is the {readable}? (e.g., California, New York)"
    
    if 'country' in lower_readable:
        return f"What is the {readable}? (e.g., United States, Canada)"
    
    # Position/Title patterns
    if any(word in lower_readable for word in ['title', 'position', 'role', 'designation']):
        return f"What is the {readable}? (e.g., CEO, Manager, Director)"
    
    # Number patterns
    if any(word in lower_readable for word in ['number', 'num', 'no', '#', 'id', 'identifier']):
        if 'tax' in lower_readable or 'ein' in lower_readable or 'ssn' in lower_readable:
            return f"What is the {readable}? (e.g., 12-3456789)"
        return f"What is the {readable}?"
    
    # Percentage patterns
    if any(word in lower_readable for word in ['percent', 'percentage', 'rate', '%']):
        return f"What is the {readable}? (e.g., 5 or 5.5)"
    
    # Description/Text patterns
    if any(word in lower_readable for word in ['description', 'details', 'notes', 'comments']):
        return f"Please provide the {readable}:"
    
    # Signature patterns
    if any(word in lower_readable for word in ['signature', 'signed', 'sign']):
        return f"What is the {readable}? (Name for signature)"
    
    # Yes/No patterns
    if any(word in lower_readable for word in ['yes/no', 'y/n', 'true/false']):
        return f"What is the {readable}? (Yes or No)"
    
    # Duration/Time patterns
    if any(word in lower_readable for word in ['duration', 'period', 'term', 'time']):
        return f"What is the {readable}? (e.g., 12 months, 2 years)"
    
    # Quantity patterns
    if any(word in lower_readable for word in ['quantity', 'count', 'total', 'units']):
        return f"What is the {readable}? (Enter a number)"
    
    # Default case - smart capitalization
    if readable.islower():
        readable = readable.capitalize()
    elif readable.isupper() and len(readable) > 3:
        readable = readable.title()
    
    return f"What is the {readable}?"


def replace_placeholders_in_docx(original_file, placeholder_values):
    """
    Universal placeholder replacement supporting all formats.
    """
    try:
        original_file.seek(0)
        doc = Document(original_file)
        
        # Replace in paragraphs
        for para in doc.paragraphs:
            for placeholder, value in placeholder_values.items():
                # All possible placeholder formats
                patterns = [
                    f'{{{{{placeholder}}}}}',  # {{placeholder}}
                    f'{{{placeholder}}}',       # {placeholder}
                    f'[{placeholder}]',         # [placeholder]
                    f'<<{placeholder}>>',       # <<placeholder>>
                ]
                
                for pattern in patterns:
                    if pattern in para.text:
                        for run in para.runs:
                            if pattern in run.text:
                                run.text = run.text.replace(pattern, str(value))
        
        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for placeholder, value in placeholder_values.items():
                        patterns = [
                            f'{{{{{placeholder}}}}}',
                            f'{{{placeholder}}}',
                            f'[{placeholder}]',
                            f'<<{placeholder}>>',
                        ]
                        
                        for pattern in patterns:
                            if pattern in cell.text:
                                for para in cell.paragraphs:
                                    for run in para.runs:
                                        if pattern in run.text:
                                            run.text = run.text.replace(pattern, str(value))
        
        # Save to BytesIO
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output
        
    except Exception as e:
        st.error(f"Error replacing placeholders: {str(e)}")
        return None


# Session state initialization
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


# Main UI
st.title("📝 Document Placeholder Filler")
st.markdown("Upload any .docx document with placeholders, and I'll help you fill them in!")

# Sidebar
with st.sidebar:
    st.header("ℹ️ How it works")
    st.markdown("""
    1. Upload a `.docx` file with placeholders
    2. Supported formats:
        - `{{placeholder}}`
        - `{placeholder}`
        - `[placeholder]`
        - `<<placeholder>>`
        - `[_______]` (blank fields)
    3. Answer questions in the chat
    4. Download your completed document
    
    **Works with any document:**
    - Contracts & Agreements
    - Forms & Applications
    - Letters & Memos
    - Legal Documents
    - HR Documents
    - And more!
    """)
    
    st.markdown("---")
    if st.button("🔄 Start Over", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# File upload
if not st.session_state.document_completed:
    uploaded_file = st.file_uploader(
        "Upload your .docx document",
        type=['docx'],
        help="Upload any Word document containing placeholders"
    )
    
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
                        display_text = placeholder if len(placeholder) < 50 else placeholder[:47] + "..."
                        st.write(f"{i}. `{display_text}`")
            else:
                st.warning("⚠️ No placeholders detected. Make sure your document contains placeholders like [name], {date}, or {{company}}.")
                st.session_state.uploaded_file = None


# Chat interface
if st.session_state.placeholders and not st.session_state.document_completed:
    st.markdown("---")
    st.header("💬 Fill in the Placeholders")
    
    # Progress indicator
    progress = st.session_state.current_placeholder_index / len(st.session_state.placeholders)
    st.progress(progress, text=f"Progress: {st.session_state.current_placeholder_index}/{len(st.session_state.placeholders)} completed")
    
    # Chat history
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message['role']):
                st.write(message['content'])
    
    # Current question
    if st.session_state.current_placeholder_index < len(st.session_state.placeholders):
        current_placeholder = st.session_state.placeholders[st.session_state.current_placeholder_index]
        
        if not st.session_state.chat_history or st.session_state.chat_history[-1]['role'] != 'assistant':
            question = generate_question_from_placeholder(current_placeholder)
            
            st.session_state.chat_history.append({
                'role': 'assistant',
                'content': f"**Question {st.session_state.current_placeholder_index + 1}/{len(st.session_state.placeholders)}:** {question}"
            })
            st.rerun()
        
        # User input
        user_input = st.chat_input(f"Your answer for placeholder #{st.session_state.current_placeholder_index + 1}...")
        
        if user_input:
            st.session_state.placeholder_values[current_placeholder] = user_input
            st.session_state.chat_history.append({
                'role': 'user',
                'content': user_input
            })
            
            st.session_state.current_placeholder_index += 1
            
            if st.session_state.current_placeholder_index >= len(st.session_state.placeholders):
                st.session_state.document_completed = True
                st.session_state.chat_history.append({
                    'role': 'assistant',
                    'content': "🎉 Perfect! All placeholders filled. Download your document below!"
                })
            
            st.rerun()


# Download section
if st.session_state.document_completed and st.session_state.original_file_bytes:
    st.markdown("---")
    st.header("✅ Document Complete!")
    
    original_file = BytesIO(st.session_state.original_file_bytes)
    completed_doc = replace_placeholders_in_docx(original_file, st.session_state.placeholder_values)
    
    if completed_doc:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("📄 Summary of Changes")
            for i, (placeholder, value) in enumerate(st.session_state.placeholder_values.items(), 1):
                display_placeholder = placeholder if len(placeholder) < 40 else placeholder[:37] + "..."
                st.write(f"{i}. **{display_placeholder}** → {value}")
        
        with col2:
            st.subheader("⬇️ Download")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            docx_filename = f"completed_{timestamp}.docx"
            
            st.download_button(
                label="📥 Download DOCX",
                data=completed_doc.getvalue(),
                file_name=docx_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
            
            st.info("💡 Convert to PDF using Word, Google Docs, or online tools")
        
        st.markdown("---")
        if st.button("✏️ Edit Answers", use_container_width=True):
            st.session_state.document_completed = False
            st.session_state.current_placeholder_index = 0
            st.session_state.chat_history = []
            st.rerun()


# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 0.9em;'>
    Made By Sushant Kumar | Universal Document Placeholder Filler
    </div>
    """,
    unsafe_allow_html=True
)
