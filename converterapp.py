import streamlit as st
import re

def fix_paragraph_block(code):
    """Fix the paragraph block section to remove nested <p> tags"""
    
    # Pattern to find the problematic paragraph block code
    old_pattern = r'''if element_name == 'p':
                    # Convert paragraphs to paragraph blocks
                    inner_html = element\.decode_contents\(\)
                    if inner_html\.strip\(\):
                        block = f"<!-- wp:paragraph -->\\n<p>\{inner_html\}</p>\\n<!-- /wp:paragraph -->"
                        blocks\.append\(block\)'''
    
    new_code = '''if element_name == 'p':
                    # Convert paragraphs to paragraph blocks
                    inner_html = element.decode_contents()
                    if inner_html.strip():
                        # FIXED: Remove any nested <p> tags from inner_html to prevent nesting
                        soup_inner = BeautifulSoup(inner_html, 'html.parser')
                        for nested_p in soup_inner.find_all('p'):
                            nested_p.unwrap()
                        cleaned_inner_html = str(soup_inner)
                        block = f"<!-- wp:paragraph -->\\n<p>{cleaned_inner_html}</p>\\n<!-- /wp:paragraph -->"
                        blocks.append(block)'''
    
    code = re.sub(old_pattern, new_code, code)
    
    return code

def fix_blockquote_block(code):
    """Fix the blockquote block section to remove nested <p> tags"""
    
    # Pattern to find the problematic blockquote block code
    old_pattern = r'''elif element_name == 'blockquote':
                    # Convert blockquotes to quote blocks
                    quote_content = element\.decode_contents\(\)
                    if quote_content\.strip\(\):
                        block = f'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>\{quote_content\}</p></blockquote>\\n<!-- /wp:quote -->'
                        blocks\.append\(block\)'''
    
    new_code = '''elif element_name == 'blockquote':
                    # Convert blockquotes to quote blocks
                    quote_content = element.decode_contents()
                    if quote_content.strip():
                        # FIXED: Remove any nested <p> tags from quote_content to prevent nesting
                        soup_quote = BeautifulSoup(quote_content, 'html.parser')
                        for nested_p in soup_quote.find_all('p'):
                            nested_p.unwrap()
                        cleaned_quote_content = str(soup_quote)
                        block = f'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{cleaned_quote_content}</p></blockquote>\\n<!-- /wp:quote -->'
                        blocks.append(block)'''
    
    code = re.sub(old_pattern, new_code, code)
    
    return code

def simple_fix(code):
    """Enhanced approach - handles multiple variations of the problematic code"""
    
    # Strategy 1: Fix the most common paragraph block pattern
    patterns_to_fix = [
        # Pattern 1: Standard format with double quotes and f-string
        (
            'inner_html = element.decode_contents()\n                    if inner_html.strip():\n                        block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"\n                        blocks.append(block)',
            'inner_html = element.decode_contents()\n                    if inner_html.strip():\n                        # FIXED: Remove any nested <p> tags from inner_html to prevent nesting\n                        soup_inner = BeautifulSoup(inner_html, \'html.parser\')\n                        for nested_p in soup_inner.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_inner_html = str(soup_inner)\n                        block = f"<!-- wp:paragraph -->\\n<p>{cleaned_inner_html}</p>\\n<!-- /wp:paragraph -->"\n                        blocks.append(block)'
        ),
        # Pattern 2: Variations with different whitespace
        (
            'if inner_html.strip():\n                        block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"',
            'if inner_html.strip():\n                        # FIXED: Remove any nested <p> tags\n                        soup_inner = BeautifulSoup(inner_html, \'html.parser\')\n                        for nested_p in soup_inner.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_inner_html = str(soup_inner)\n                        block = f"<!-- wp:paragraph -->\\n<p>{cleaned_inner_html}</p>\\n<!-- /wp:paragraph -->"'
        ),
    ]
    
    # Apply paragraph fixes
    for old_pattern, new_pattern in patterns_to_fix:
        if old_pattern in code:
            code = code.replace(old_pattern, new_pattern)
    
    # Strategy 2: Fix blockquote blocks
    quote_patterns = [
        # Pattern 1: Standard blockquote format
        (
            'quote_content = element.decode_contents()\n                    if quote_content.strip():\n                        block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'\n                        blocks.append(block)',
            'quote_content = element.decode_contents()\n                    if quote_content.strip():\n                        # FIXED: Remove any nested <p> tags from quote_content to prevent nesting\n                        soup_quote = BeautifulSoup(quote_content, \'html.parser\')\n                        for nested_p in soup_quote.find_all(\'p\'):\n                            nested_p.unwrap()\n                        cleaned_quote_content = str(soup_quote)\n                        block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{cleaned_quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'\n                        blocks.append(block)'
        ),
    ]
    
    # Apply blockquote fixes
    for old_pattern, new_pattern in quote_patterns:
        if old_pattern in code:
            code = code.replace(old_pattern, new_pattern)
    
    return code

def analyze_code(code):
    """Analyze the code to detect issues"""
    issues = []
    fixes_needed = []
    
    # Check for paragraph block issues
    if 'block = f"<!-- wp:paragraph -->\\n<p>{inner_html}</p>\\n<!-- /wp:paragraph -->"' in code:
        if 'soup_inner = BeautifulSoup(inner_html' not in code:
            issues.append("⚠️ Found problematic paragraph block code (creates nested <p> tags)")
            fixes_needed.append("paragraph")
        else:
            issues.append("✅ Paragraph block already has nested tag fix")
    
    # Check for blockquote block issues
    if 'block = f\'<!-- wp:quote -->\\n<blockquote class="wp-block-quote"><p>{quote_content}</p></blockquote>\\n<!-- /wp:quote -->\'' in code:
        if 'soup_quote = BeautifulSoup(quote_content' not in code:
            issues.append("⚠️ Found problematic blockquote block code (creates nested <p> tags)")
            fixes_needed.append("blockquote")
        else:
            issues.append("✅ Blockquote block already has nested tag fix")
    
    # Look for the function signature
    if 'def convert_html_to_gutenberg_blocks' in code:
        issues.append("✅ Found convert_html_to_gutenberg_blocks function")
    else:
        issues.append("⚠️ Function 'convert_html_to_gutenberg_blocks' not found - make sure you paste the complete function")
    
    # Summary
    if fixes_needed:
        issues.append(f"🔧 {len(fixes_needed)} fix(es) will be applied: {', '.join(fixes_needed)}")
    elif "⚠️" not in str(issues):
        issues.append("🎉 Code looks good! No fixes needed.")
    
    return issues

# Streamlit App
st.set_page_config(
    page_title="WordPress Gutenberg Code Fixer",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 WordPress Gutenberg Block Converter Fixer")
st.markdown("""
This tool fixes the **nested `<p>` tag issue** in WordPress Gutenberg block converter functions.

**The Problem:** Your WordPress posts show this error:
> ⚠️ "Block contains unexpected or invalid content"

**The Cause:** Google Docs creates nested paragraph tags like: `<p><span><p>content</p></span></p>`

**The Solution:** This tool automatically adds code to unwrap nested tags, producing: `<p><span>content</span></p>`

---
""")

# Create two columns
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 Input: Your Old Code")
    st.markdown("Paste your `convert_html_to_gutenberg_blocks` function here:")
    
    input_code = st.text_area(
        "Code Input",
        height=500,
        placeholder="Paste your function code here...",
        label_visibility="collapsed"
    )
    
    if st.button("🔍 Analyze & Fix Code", type="primary", use_container_width=True):
        if input_code:
            st.session_state['input_code'] = input_code
            st.session_state['fixed_code'] = simple_fix(input_code)
            st.session_state['issues'] = analyze_code(input_code)
        else:
            st.warning("Please paste your code first!")

with col2:
    st.subheader("📤 Output: Fixed Code")
    
    if 'fixed_code' in st.session_state:
        # Show analysis
        st.markdown("#### 🔍 Analysis Results:")
        for issue in st.session_state['issues']:
            if "⚠️" in issue:
                st.warning(issue)
            elif "🔧" in issue:
                st.info(issue)
            elif "🎉" in issue:
                st.success(issue)
            else:
                st.success(issue)
        
        # Show before/after example
        st.markdown("---")
        st.markdown("#### 🔄 Before/After Preview:")
        
        with st.expander("See what the fix does (Example)", expanded=False):
            col_before, col_after = st.columns(2)
            
            with col_before:
                st.markdown("**❌ Before (Broken):**")
                st.code('''<!-- wp:paragraph -->
<p><span><p>Content here</p></span></p>
<!-- /wp:paragraph -->

Result: Nested <p> tags
→ WordPress error!''', language='html')
            
            with col_after:
                st.markdown("**✅ After (Fixed):**")
                st.code('''<!-- wp:paragraph -->
<p><span>Content here</span></p>
<!-- /wp:paragraph -->

Result: Clean HTML
→ WordPress works!''', language='html')
        
        st.markdown("---")
        st.markdown("#### ✅ Fixed Code:")
        
        # Display fixed code
        st.code(st.session_state['fixed_code'], language='python', line_numbers=True)
        
        # Download button
        st.download_button(
            label="📥 Download Fixed Code",
            data=st.session_state['fixed_code'],
            file_name="fixed_gutenberg_converter.py",
            mime="text/x-python",
            use_container_width=True
        )
        
        # Show changes
        with st.expander("📋 What Changed?"):
            st.markdown("""
            **Changes Applied:**
            
            1. **Paragraph Blocks Fix:**
               ```python
               # ADDED THIS CODE:
               soup_inner = BeautifulSoup(inner_html, 'html.parser')
               for nested_p in soup_inner.find_all('p'):
                   nested_p.unwrap()
               cleaned_inner_html = str(soup_inner)
               ```
               - Detects nested `<p>` tags
               - Unwraps them (removes tag, keeps content)
               - Produces clean HTML structure
            
            2. **Blockquote Blocks Fix:**
               ```python
               # ADDED THIS CODE:
               soup_quote = BeautifulSoup(quote_content, 'html.parser')
               for nested_p in soup_quote.find_all('p'):
                   nested_p.unwrap()
               cleaned_quote_content = str(soup_quote)
               ```
               - Same fix for blockquote elements
               - Prevents nesting in quotes too
            
            **Why This Fixes WordPress:**
            - WordPress visual editor cannot parse nested `<p>` tags
            - Shows "Block contains unexpected or invalid content" error
            - This fix prevents the nesting issue at the source
            
            **Example Transformation:**
            ```
            INPUT:  <p><span><p>Text</p></span></p>
            OUTPUT: <p><span>Text</span></p>
            ```
            """)
    else:
        st.info("👈 Paste your code in the left panel and click 'Analyze & Fix Code'")

# Sidebar with information
with st.sidebar:
    st.header("ℹ️ About This Tool")
    st.markdown("""
    ### What Does This Fix?
    
    This tool fixes WordPress Gutenberg block converters that create nested paragraph tags.
    
    
    ### When to Use This
    - ✅ WordPress visual editor shows errors
    - ✅ Content appears fine in code editor
    - ✅ Google Docs export creates issues
    - ✅ Posts won't save or publish correctly
    
    ### How It Works
    The fix uses BeautifulSoup to:
    1. Parse inner HTML content
    2. Find all nested `<p>` tags
    3. Unwrap them (remove tag, keep content)
    4. Return clean HTML
    """)
    
    st.markdown("---")
    
    # Test HTML Transformation Section
    st.header("🧪 Test the Fix")
    st.markdown("See how the fix transforms HTML:")
    
    test_html = st.text_area(
        "Paste HTML to test:",
        value='<span><p>Test content here</p></span>',
        height=100,
        key="test_html"
    )
    
    if st.button("🔬 Transform HTML", key="test_button"):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(test_html, 'html.parser')
            for nested_p in soup.find_all('p'):
                nested_p.unwrap()
            result = str(soup)
            
            st.success("Transformed HTML:")
            st.code(result, language='html')
            
            if '<p>' in test_html and '<p>' not in result:
                st.info("✅ Nested <p> tags removed!")
            elif '<p>' not in test_html:
                st.info("ℹ️ No <p> tags found to unwrap")
            else:
                st.info("ℹ️ HTML structure preserved")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    
    st.markdown("---")
    st.success("Made with ❤️ for Content Team")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>💡 <strong>Pro Tip:</strong> Always test your fixed code in a development environment first!</p>
</div>
""", unsafe_allow_html=True)
