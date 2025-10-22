import streamlit as st
import re

def fix_code(code):
    """Fix nested <p> tag issues in Gutenberg block converter code"""
    
    # Fix paragraph blocks
    paragraph_patterns = [
        (
            'inner_html = element.decode_contents()\n                    if inner_html.strip():\n                        block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"\n                        blocks.append(block)',
            'inner_html = element.decode_contents()\n                    if inner_html.strip():\n                        soup_inner = BeautifulSoup(inner_html, \'html.parser\')\n                        for nested_p in soup_inner.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_inner_html = str(soup_inner)\n                        block = f"<!-- wp:paragraph -->\\n<p>{cleaned_inner_html}</p>\\n<!-- /wp:paragraph -->"\n                        blocks.append(block)'
        ),
        (
            'if inner_html.strip():\n                        block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"',
            'if inner_html.strip():\n                        soup_inner = BeautifulSoup(inner_html, \'html.parser\')\n                        for nested_p in soup_inner.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_inner_html = str(soup_inner)\n                        block = f"<!-- wp:paragraph -->\\n<p>{cleaned_inner_html}</p>\\n<!-- /wp:paragraph -->"'
        ),
    ]
    
    # Fix blockquote blocks
    quote_patterns = [
        (
            'quote_content = element.decode_contents()\n                    if quote_content.strip():\n                        block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'\n                        blocks.append(block)',
            'quote_content = element.decode_contents()\n                    if quote_content.strip():\n                        soup_quote = BeautifulSoup(quote_content, \'html.parser\')\n                        for nested_p in soup_quote.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_quote_content = str(soup_quote)\n                        block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{cleaned_quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'\n                        blocks.append(block)'
        ),
    ]
    
    # Apply fixes
    for old, new in paragraph_patterns:
        if old in code:
            code = code.replace(old, new)
    
    for old, new in quote_patterns:
        if old in code:
            code = code.replace(old, new)
    
    return code

def analyze_code(code):
    """Analyze code for issues"""
    issues = []
    
    has_paragraph_issue = 'block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"' in code
    has_paragraph_fix = 'soup_inner = BeautifulSoup(inner_html' in code
    
    has_quote_issue = 'block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'' in code
    has_quote_fix = 'soup_quote = BeautifulSoup(quote_content' in code
    
    if has_paragraph_issue and not has_paragraph_fix:
        issues.append("Paragraph blocks need fixing")
    elif has_paragraph_issue and has_paragraph_fix:
        issues.append("Paragraph blocks already fixed")
    
    if has_quote_issue and not has_quote_fix:
        issues.append("Blockquote blocks need fixing")
    elif has_quote_issue and has_quote_fix:
        issues.append("Blockquote blocks already fixed")
    
    return issues

# Streamlit App
st.set_page_config(
    page_title="Gutenberg Code Fixer",
    page_icon="🔧",
    layout="wide"
)

st.title("WordPress Gutenberg Block Fixer")
st.markdown("Fix nested `<p>` tag issues in your Gutenberg block converter")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input Code")
    input_code = st.text_area(
        "Paste your convert_html_to_gutenberg_blocks function:",
        height=500,
        placeholder="Paste function code here...",
        label_visibility="visible"
    )
    
    if st.button("Fix Code", type="primary", use_container_width=True):
        if input_code:
            st.session_state['input_code'] = input_code
            st.session_state['fixed_code'] = fix_code(input_code)
            st.session_state['issues'] = analyze_code(input_code)
        else:
            st.warning("Please paste your code first")

with col2:
    st.subheader("Fixed Code")
    
    if 'fixed_code' in st.session_state:
        # Show analysis
        issues = st.session_state['issues']
        if issues:
            for issue in issues:
                if "need fixing" in issue:
                    st.warning(f"⚠️ {issue}")
                else:
                    st.success(f"✅ {issue}")
        else:
            st.success("✅ No issues found")
        
        st.markdown("---")
        
        # Display fixed code
        st.code(st.session_state['fixed_code'], language='python', line_numbers=True)
        
        # Download button
        st.download_button(
            label="Download Fixed Code",
            data=st.session_state['fixed_code'],
            file_name="fixed_gutenberg_converter.py",
            mime="text/x-python",
            use_container_width=True
        )
    else:
        st.info("Paste your code and click 'Fix Code'")

st.markdown("---")
st.caption("Fixes: `<p><span><p>content</p></span></p>` → `<p><span>content</span></p>`")
