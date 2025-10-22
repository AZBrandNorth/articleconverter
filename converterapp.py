import streamlit as st

# Try to import BeautifulSoup with error handling
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    st.error("""
    ⚠️ **Missing Required Package: beautifulsoup4**
    
    **For Streamlit Cloud:**
    1. Make sure `requirements.txt` is in your GitHub repository root
    2. The file should contain: `beautifulsoup4==4.12.3`
    3. Click 'Reboot app' in Streamlit Cloud
    4. Wait 2-3 minutes for installation
    
    **For Local Use:**
    ```bash
    pip install beautifulsoup4 lxml
    ```
    """)
    st.stop()

def fix_html_content(html_content):
    """Fix nested <p> tags in WordPress HTML content"""
    
    # Parse the HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all paragraph tags
    for p_tag in soup.find_all('p'):
        # Check if there are nested <p> tags inside
        nested_p_tags = p_tag.find_all('p')
        
        if nested_p_tags:
            # Unwrap each nested <p> tag (remove the tag but keep its content)
            for nested_p in nested_p_tags:
                nested_p.unwrap()
    
    # Return the cleaned HTML
    return str(soup)

def count_issues(html_content):
    """Count how many nested <p> tag issues exist"""
    soup = BeautifulSoup(html_content, 'html.parser')
    issue_count = 0
    
    for p_tag in soup.find_all('p'):
        nested_p_tags = p_tag.find_all('p')
        if nested_p_tags:
            issue_count += len(nested_p_tags)
    
    return issue_count

# Streamlit App
st.set_page_config(
    page_title="HTML Content Fixer",
    page_icon="🔧",
    layout="wide"
)

st.title("WordPress HTML Content Fixer")
st.markdown("Fix nested `<p>` tags in your WordPress content")

# Show package status
with st.expander("📦 System Status", expanded=False):
    if BS4_AVAILABLE:
        st.success("✅ All required packages installed")
    else:
        st.error("❌ beautifulsoup4 is missing")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input HTML")
    input_html = st.text_area(
        "Paste your WordPress HTML content:",
        height=500,
        placeholder="Paste HTML content here...",
        label_visibility="visible"
    )
    
    if st.button("Fix HTML", type="primary", use_container_width=True):
        if input_html:
            issue_count = count_issues(input_html)
            st.session_state['input_html'] = input_html
            st.session_state['fixed_html'] = fix_html_content(input_html)
            st.session_state['issue_count'] = issue_count
        else:
            st.warning("Please paste your HTML content first")

with col2:
    st.subheader("Fixed HTML")
    
    if 'fixed_html' in st.session_state:
        # Show issue count
        issue_count = st.session_state['issue_count']
        if issue_count > 0:
            st.warning(f"⚠️ Found and fixed {issue_count} nested <p> tag(s)")
        else:
            st.success("✅ No nested <p> tags found")
        
        st.markdown("---")
        
        # Show before/after example
        if issue_count > 0:
            with st.expander("Example Fix", expanded=True):
                col_before, col_after = st.columns(2)
                
                with col_before:
                    st.markdown("**Before:**")
                    st.code('<p><span><p>Content</p></span></p>', language='html')
                
                with col_after:
                    st.markdown("**After:**")
                    st.code('<p><span>Content</span></p>', language='html')
        
        st.markdown("---")
        
        # Display fixed HTML
        st.code(st.session_state['fixed_html'], language='html')
        
        # Download button
        st.download_button(
            label="Download Fixed HTML",
            data=st.session_state['fixed_html'],
            file_name="fixed_wordpress_content.html",
            mime="text/html",
            use_container_width=True
        )
    else:
        st.info("Paste your HTML and click 'Fix HTML'")

st.markdown("---")
st.caption("Removes nested paragraph tags to fix WordPress editor errors")
