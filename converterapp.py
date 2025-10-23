# app.py
# WordPress HTML Content Fixer - Enhanced Version with Gutenberg Comment Fix
# - Removes nested <p>, optional empty <p>, and <p> wrapping block elements
# - Preserves Gutenberg block comments, strips document wrapper
# - Removes empty Gutenberg blocks (<!-- wp:* -->...<!-- /wp:* -->)
# - Removes <p> wrappers that contain ONLY Gutenberg comments (and optional <br>/whitespace)
# - FIXES: Gutenberg comments with extra spaces and comments inside <p> tags
# - Enhanced with error handling, validation, presets, and detailed statistics

import streamlit as st
import difflib
from typing import Optional, Dict, List, Tuple
import re

# ---------------- Imports with graceful fallbacks ----------------
PARSER_ORDER = []
try:
    from bs4 import BeautifulSoup, NavigableString, Tag, Comment
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import html5lib  # noqa: F401
    PARSER_ORDER.append("html5lib")
except Exception:
    pass

try:
    import lxml  # noqa: F401
    PARSER_ORDER.append("lxml")
except Exception:
    pass

PARSER_ORDER.append("html.parser")  # always available

# ---------------- Constants ----------------
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
PREVIEW_LENGTH = 500
FULL_DISPLAY_THRESHOLD = 10000

# ---------------- App Config ----------------
st.set_page_config(page_title="HTML Content Fixer", page_icon="🔧", layout="wide")

# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 10px;
        margin: 10px 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 10px;
        margin: 10px 0;
    }
    .error-box {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

if not BS4_AVAILABLE:
    with st.expander("📦 System Status", expanded=True):
        st.error("❌ beautifulsoup4 is missing")
        st.write("**Parsers (best → fallback):**", ", ".join(PARSER_ORDER))
        st.info(
            "Add to `requirements.txt` in repo root:\n\n"
            "- streamlit==1.39.0\n- beautifulsoup4==4.12.3\n- lxml==5.3.0\n- html5lib==1.1\n\n"
            "Then Reboot (full rebuild) in Streamlit Cloud."
        )
    st.stop()

# ---------------- Utilities ----------------
BLOCK_LEVEL_TAGS = {
    "div", "section", "article", "aside", "header", "footer", "main", "nav",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "figure", "figcaption",
    "blockquote", "pre", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6"
}
NON_EMPTY_INLINE_OK = {"img", "svg", "iframe", "video", "audio", "canvas", "embed", "object"}

def pick_parser() -> str:
    return PARSER_ORDER[0] if PARSER_ORDER else "html.parser"

def is_effectively_empty(tag: Tag) -> bool:
    """
    True if <p> has no visible text and no meaningful inline content (br is ignored).
    This includes paragraphs with only empty inline tags like <span></span>, <em></em>, etc.
    """
    for child in tag.children:
        if isinstance(child, Tag):
            if child.name == "br":
                continue  # ignore line breaks
            if child.name in NON_EMPTY_INLINE_OK:
                return False  # has meaningful media content
            
            # Recursively check if the child tag has any content
            # This catches empty <span>, <em>, <strong>, <a>, etc.
            child_text = child.get_text(separator="", strip=True)
            child_text = child_text.replace("\xa0", "").replace("&nbsp;", "").strip()
            if child_text:
                return False  # child has text content
            
            # Check if child has any meaningful descendants (images, etc.)
            if any(isinstance(d, Tag) and d.name in NON_EMPTY_INLINE_OK for d in child.descendants):
                return False
                
        if isinstance(child, NavigableString) and child.strip():
            return False
    
    # Final check: get all text from tag and descendants
    text = tag.get_text(separator="", strip=True)
    text = text.replace("\xa0", "").replace("&nbsp;", "").strip()
    return text == ""

def unwrap_children(tag: Tag, child_name: str) -> int:
    """Unwrap specific nested children of a tag (used for nested <p>)."""
    changed = 0
    nested = tag.find_all(child_name, recursive=True)
    for n in nested:
        if n is not tag:
            n.unwrap()
            changed += 1
    return changed

def unwrap_p_around_block(p_tag: Tag) -> int:
    """If a <p> wraps block-level tags, unwrap the <p> entirely."""
    for c in p_tag.children:
        if isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS:
            p_tag.unwrap()
            return 1
    return 0

def p_is_wp_comment_wrapper(p: Tag) -> bool:
    """
    Return True if this <p> contains ONLY:
      - Gutenberg comments like <!-- wp:... --> or <!-- /wp:... -->
      - optional <br> tags
      - whitespace / NBSP
    """
    for child in p.contents:
        if isinstance(child, NavigableString):
            if str(child).replace("\xa0", " ").strip():
                return False
        elif isinstance(child, Comment):
            s = str(child).strip()
            if not (s.startswith("wp:") or s.startswith("/wp:")):
                return False
        elif isinstance(child, Tag):
            if child.name == "br":
                continue
            return False
        else:
            return False
    return True

def extract_comments_from_p_tags(soup: BeautifulSoup) -> int:
    """
    Extract Gutenberg comments that are wrongly placed inside <p> tags.
    Move them outside the <p> tags to their proper location.
    """
    fixed_count = 0
    
    for p in soup.find_all("p"):
        # Find all comment children
        comments_to_move = []
        for child in list(p.children):
            if isinstance(child, Comment):
                comment_text = str(child).strip()
                if comment_text.startswith("wp:") or comment_text.startswith("/wp:"):
                    comments_to_move.append(child)
        
        if comments_to_move:
            # Move comments outside the paragraph
            for comment in comments_to_move:
                # Extract the comment
                comment.extract()
                # Insert it after the paragraph
                p.insert_after(comment)
                fixed_count += 1
            
            # If paragraph is now empty (only had comments and maybe br tags), remove it
            if is_effectively_empty(p):
                p.decompose()
    
    return fixed_count

def normalize_paragraphs(soup: BeautifulSoup, remove_empty: bool, unwrap_block_wrapped_p: bool):
    """
    Recursively:
      - Extract Gutenberg comments from inside <p> tags
      - Unwrap nested <p> inside <p>
      - Remove <p> that are ONLY Gutenberg comment wrappers
      - Optionally remove empty <p>
      - Optionally unwrap <p> that wrap block-level elements
    """
    total_nested_fixes = 0
    total_empty_removed = 0
    total_unwrapped_block = 0
    total_wp_comment_wrapper_removed = 0
    total_comments_extracted = 0
    changed = True
    safety_counter = 0

    # First pass: extract comments from inside p tags
    total_comments_extracted = extract_comments_from_p_tags(soup)

    while changed and safety_counter < 50:
        changed = False
        safety_counter += 1
        p_tags = list(soup.find_all("p"))
        for p in p_tags:
            # 1) remove pure Gutenberg-comment wrappers
            if p_is_wp_comment_wrapper(p):
                p.decompose()
                total_wp_comment_wrapper_removed += 1
                changed = True
                continue

            # 2) unwrap nested <p> within <p>
            nested_count = unwrap_children(p, "p")
            if nested_count:
                total_nested_fixes += nested_count
                changed = True

            # 3) unwrap <p> that contains block elements
            if unwrap_block_wrapped_p and p.parent:
                unwrapped = unwrap_p_around_block(p)
                if unwrapped:
                    total_unwrapped_block += unwrapped
                    changed = True
                    continue

            # 4) remove empty <p>
            if remove_empty and p and p.name == "p" and is_effectively_empty(p):
                p.decompose()
                total_empty_removed += 1
                changed = True

    return {
        "nested_p_fixed": total_nested_fixes,
        "empty_p_removed": total_empty_removed,
        "block_wraps_unwrapped": total_unwrapped_block,
        "wp_comment_wrapper_removed": total_wp_comment_wrapper_removed,
        "comments_extracted_from_p": total_comments_extracted,
        "iterations": safety_counter
    }

def _node_has_visible_content(node: object) -> bool:
    """Does this node (or any of its descendants) render something visible?"""
    if isinstance(node, NavigableString):
        return bool(str(node).strip())
    if isinstance(node, Comment):
        return False
    if isinstance(node, Tag):
        if node.name in {"img", "svg", "video", "audio", "canvas", "iframe", "object", "embed"}:
            return True
        if node.get_text(strip=True):
            return True
        for d in node.descendants:
            if isinstance(d, Tag) and d.name in {"img", "svg", "video", "audio", "canvas", "iframe", "object", "embed"}:
                return True
            if isinstance(d, NavigableString) and str(d).strip():
                return True
        return False
    return False

def remove_empty_gutenberg_blocks(soup: BeautifulSoup) -> int:
    """Remove empty Gutenberg blocks at the top level."""
    container = soup.body if getattr(soup, "body", None) else soup
    removed = 0
    i = 0
    nodes = list(container.children)

    while i < len(nodes):
        n = nodes[i]
        if isinstance(n, Comment) and str(n).strip().startswith("wp:"):
            j = i + 1
            content_has_any = False
            while j < len(nodes):
                m = nodes[j]
                if isinstance(m, Comment) and str(m).strip().startswith("/wp:"):
                    break
                if _node_has_visible_content(m):
                    content_has_any = True
                j += 1

            if j < len(nodes) and not content_has_any:
                for k in range(i, j + 1):
                    try:
                        nodes[k].extract()
                    except Exception:
                        pass
                removed += 1
                nodes = list(container.children)
                continue
        i += 1
    return removed

def analyze_issues(html: str, parser: str) -> Dict:
    """Analyze HTML for common issues."""
    try:
        soup = BeautifulSoup(html, parser)
        nested = 0
        block_wraps = 0
        empties = 0
        empty_with_span = 0
        wp_comment_wrappers = 0
        comments_in_p = 0
        
        for p in soup.find_all("p"):
            nested += len(p.find_all("p"))
            if any(isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS for c in p.children):
                block_wraps += 1
            
            # Check if empty
            if is_effectively_empty(p):
                empties += 1
                # Check if it has span tags (even if empty)
                if p.find("span"):
                    empty_with_span += 1
            
            if p_is_wp_comment_wrapper(p):
                wp_comment_wrappers += 1
            
            # Count WP comments inside p tags
            for child in p.children:
                if isinstance(child, Comment):
                    comment_text = str(child).strip()
                    if comment_text.startswith("wp:") or comment_text.startswith("/wp:"):
                        comments_in_p += 1
        
        return {
            "nested_p": nested,
            "p_wrapping_blocks": block_wraps,
            "empty_p": empties,
            "empty_p_with_span": empty_with_span,
            "wp_comment_wrappers": wp_comment_wrappers,
            "wp_comments_in_p": comments_in_p
        }
    except Exception as e:
        return {"error": str(e)}

def validate_html(html: str, parser: str) -> Dict:
    """Validate that HTML has been properly fixed."""
    try:
        soup = BeautifulSoup(html, parser)
        issues = []
        
        # Check for nested <p> tags
        for p in soup.find_all("p"):
            if p.find("p"):
                issues.append("Still contains nested <p> tags")
                break
        
        # Check for <p> wrapping block elements
        for p in soup.find_all("p"):
            if any(isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS for c in p.children):
                issues.append("Still has <p> wrapping block elements")
                break
        
        # Check for WP comments inside <p> tags
        for p in soup.find_all("p"):
            for child in p.children:
                if isinstance(child, Comment):
                    comment_text = str(child).strip()
                    if comment_text.startswith("wp:") or comment_text.startswith("/wp:"):
                        issues.append("Still has Gutenberg comments inside <p> tags")
                        break
            if issues and "Gutenberg comments" in issues[-1]:
                break
        
        return {
            "valid": len(issues) == 0,
            "issues": issues if issues else ["All checks passed"]
        }
    except Exception as e:
        return {
            "valid": False,
            "issues": [f"Validation error: {str(e)}"]
        }

def serialize_fragment(soup: BeautifulSoup, strip_document_wrapper: bool = True, prettify: bool = False) -> str:
    """
    Return HTML suitable for Gutenberg.
    CRITICAL FIX: Remove extra spaces from Gutenberg comments.
    """
    def to_html(node) -> str:
        if isinstance(node, Comment):
            comment_text = str(node).strip()
            # Fix: Remove extra spaces in Gutenberg comments
            if comment_text.startswith("wp:") or comment_text.startswith("/wp:"):
                # Return without extra spaces
                return f"<!--{comment_text}-->"
            return f"<!-- {comment_text} -->"
        return str(node)

    if strip_document_wrapper and getattr(soup, "body", None):
        parts = []
        for node in soup.body.children:
            if isinstance(node, NavigableString) and not str(node).strip():
                continue
            parts.append(to_html(node))
        html = "\n".join(parts).strip()
    else:
        html = str(soup)

    # Additional regex cleanup for any remaining malformed comments
    # Fix: <!--  wp:  --> to <!-- wp: -->
    html = re.sub(r'<!--\s+(/?wp:[^>]+?)\s+-->', r'<!--\1-->', html)
    
    if prettify:
        return BeautifulSoup(html, "html.parser").prettify()
    return html

def fix_html_content(
    html: str,
    remove_empty: bool = True,
    unwrap_block_wrapped_p: bool = True,
    prettify: bool = False,
    parser: str | None = None,
    strip_document_wrapper: bool = True
) -> Tuple[str, Dict, str]:
    """Main fix function with error handling."""
    try:
        # Validate input
        if not html or not html.strip():
            return html, {"error": "Empty HTML provided"}, parser or pick_parser()
        
        if len(html) < 10:
            return html, {"warning": "HTML seems too short - might be incomplete"}, parser or pick_parser()
        
        parser = parser or pick_parser()
        soup = BeautifulSoup(html, parser)

        stats = normalize_paragraphs(
            soup,
            remove_empty=remove_empty,
            unwrap_block_wrapped_p=unwrap_block_wrapped_p
        )

        # Remove empty Gutenberg blocks
        stats["empty_wp_blocks_removed"] = remove_empty_gutenberg_blocks(soup)

        fixed = serialize_fragment(
            soup,
            strip_document_wrapper=strip_document_wrapper,
            prettify=prettify
        )
        
        # FINAL CLEANUP: Simple find-and-replace to remove unwanted patterns
        # This catches edge cases that might have been missed
        before_final_cleanup = fixed
        
        # 1. Remove empty p-span tags
        fixed = re.sub(r'<p>\s*<span>\s*</span>\s*</p>\s*', '', fixed)
        fixed = re.sub(r'<p><span></span></p>\s*', '', fixed)
        
        # 2. Remove consecutive Gutenberg comment pairs
        # Pattern: <!--/wp:paragraph-->\n<!-- wp:paragraph -->
        fixed = re.sub(r'<!--/wp:paragraph-->\s*<!--\s*wp:paragraph\s*-->', '', fixed)
        fixed = re.sub(r'<!--\s*/wp:paragraph\s*-->\s*<!--\s*wp:paragraph\s*-->', '', fixed)
        
        # Count how many were removed in final cleanup
        empty_span_count = before_final_cleanup.count('<p><span></span></p>')
        comment_pairs_removed = before_final_cleanup.count('<!--/wp:paragraph-->') - fixed.count('<!--/wp:paragraph-->')
        
        if empty_span_count > 0:
            stats["final_cleanup_empty_span"] = empty_span_count
        if comment_pairs_removed > 0:
            stats["final_cleanup_comment_pairs"] = comment_pairs_removed
        
        return fixed, stats, parser
    
    except Exception as e:
        return html, {"error": f"Processing failed: {str(e)}"}, parser or pick_parser()

def generate_diff(original: str, fixed: str, max_lines: int = 50) -> str:
    """Generate a unified diff between original and fixed HTML."""
    try:
        diff = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile='Original',
            tofile='Fixed',
            lineterm=''
        ))
        
        if len(diff) > max_lines:
            diff = diff[:max_lines] + [f'\n... (truncated, {len(diff) - max_lines} more lines)']
        
        return ''.join(diff) if diff else "No differences found"
    except Exception as e:
        return f"Error generating diff: {str(e)}"

# ---------------- Test Cases ----------------
def run_tests() -> Dict[str, bool]:
    """Run test cases to verify functionality."""
    test_cases = {
        "nested_p": {
            "input": "<p><p>Test</p></p>",
            "check": lambda fixed: "<p><p>" not in fixed
        },
        "empty_p": {
            "input": "<p></p><p>Content</p>",
            "check": lambda fixed: fixed.count("<p>") == 1
        },
        "empty_p_with_span": {
            "input": "<p><span></span></p><p>Content</p>",
            "check": lambda fixed: "<span></span>" not in fixed and fixed.count("<p>") == 1
        },
        "empty_p_with_nested_empty_tags": {
            "input": "<p><span><em></em></span></p><p>Content</p>",
            "check": lambda fixed: fixed.count("<p>") == 1
        },
        "p_wrap_div": {
            "input": "<p><div>Block content</div></p>",
            "check": lambda fixed: "<p><div>" not in fixed
        },
        "wp_comment_wrapper": {
            "input": "<p><!-- wp:paragraph --></p>",
            "check": lambda fixed: "<p><!--" not in fixed
        },
        "wp_comment_inside_p": {
            "input": "<p>Text<!-- wp:paragraph -->more text</p>",
            "check": lambda fixed: "<p>Text<!--" not in fixed and "<!--wp:paragraph-->" in fixed
        },
        "wp_comment_spacing": {
            "input": "<!--  wp:paragraph  --><p>Content</p><!--  /wp:paragraph  -->",
            "check": lambda fixed: "<!--wp:paragraph-->" in fixed and "<!--/wp:paragraph-->" in fixed
        },
        "multiple_nested": {
            "input": "<p><p><p>Deep nest</p></p></p>",
            "check": lambda fixed: fixed.count("<p>") == 1
        }
    }
    
    results = {}
    for name, test in test_cases.items():
        try:
            fixed, _, _ = fix_html_content(test["input"])
            results[name] = test["check"](fixed)
        except Exception:
            results[name] = False
    
    return results

# ---------------- UI ----------------
st.title("🔧 WordPress HTML Content Fixer")
st.markdown(
    "Fix nested `<p>` tags, remove empty/bridge `<p>`, unwrap `<p>` around block elements, "
    "**extract Gutenberg comments from inside paragraphs**, and output a **Gutenberg-safe fragment** "
    "(preserves block comments with proper spacing, no `<html>/<body>`). "
    "Also removes **empty Gutenberg blocks** and `<p>` wrappers that contain only Gutenberg comments."
)

st.info("🆕 **New Features**: Automatically extracts Gutenberg comments from inside `<p>` tags, removes extra spaces in comment syntax, **performs final cleanup to remove all `<p><span></span></p>` tags AND consecutive Gutenberg comment pairs!**")

with st.expander("📦 System Status", expanded=False):
    st.write("**Parsers (best → fallback):**", ", ".join(PARSER_ORDER))
    st.success("✅ BeautifulSoup available")
    st.info(f"**Max file size:** {MAX_FILE_SIZE / (1024*1024):.0f}MB")

# Sidebar - Presets
st.sidebar.header("⚙️ Settings")

preset = st.sidebar.radio(
    "Quick Presets:",
    ["🛡️ Conservative (safe)", "⚡ Aggressive (thorough)", "🎛️ Custom"],
    help="Conservative: Only fixes nested <p>. Aggressive: Fixes everything."
)

if preset == "🛡️ Conservative (safe)":
    remove_empty_opt = False
    unwrap_block_opt = True
    prettify_opt = False
    strip_wrapper_opt = True
elif preset == "⚡ Aggressive (thorough)":
    remove_empty_opt = True
    unwrap_block_opt = True
    prettify_opt = False
    strip_wrapper_opt = True
else:  # Custom
    st.sidebar.markdown("**Custom Options:**")
    remove_empty_opt = st.sidebar.checkbox("Remove empty paragraphs", value=True)
    unwrap_block_opt = st.sidebar.checkbox("Unwrap <p> that wrap block elements", value=True)
    prettify_opt = st.sidebar.checkbox("Prettify output (formatted)", value=False)
    strip_wrapper_opt = st.sidebar.checkbox("Strip <html>/<body> wrapper (recommended)", value=True)

parser_choice = st.sidebar.selectbox("Parser to use", options=["auto"] + PARSER_ORDER, index=0)

# Advanced Options
with st.sidebar.expander("🔬 Advanced Options"):
    show_validation = st.checkbox("Show validation results", value=True)
    show_diff = st.checkbox("Show before/after diff", value=False)
    run_test_suite = st.checkbox("Run test suite", value=False)

st.sidebar.markdown("---")
st.sidebar.caption("Enhanced version with Gutenberg comment fix + final regex cleanup • v2.3")

# Main content area
col1, col2 = st.columns([1, 1])

# -------- Left: Input --------
with col1:
    st.subheader("📝 Input HTML")
    input_html = st.text_area(
        "Paste your HTML:",
        height=320,
        placeholder="Paste WordPress HTML content here…",
        help="Paste the HTML content that needs fixing"
    )

    uploaded_files = st.file_uploader(
        "…or upload .html/.htm/.txt files",
        type=["html", "htm", "txt"],
        accept_multiple_files=True,
        help="Upload one or more HTML files for batch processing"
    )

    run_btn = st.button("🚀 Fix HTML", type="primary", use_container_width=True)

# -------- Right: Output --------
with col2:
    st.subheader("✨ Fixed HTML")

    if run_btn:
        selected_parser = None if parser_choice == "auto" else parser_choice

        # Run test suite if enabled
        if run_test_suite:
            with st.expander("🧪 Test Suite Results", expanded=True):
                test_results = run_tests()
                passed = sum(test_results.values())
                total = len(test_results)
                
                st.metric("Tests Passed", f"{passed}/{total}")
                
                for test_name, passed in test_results.items():
                    icon = "✅" if passed else "❌"
                    st.write(f"{icon} **{test_name}**: {'Passed' if passed else 'Failed'}")

        # Batch files
        if uploaded_files:
            st.markdown("### 📊 Batch Processing Results")
            
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_stats = []
            
            for idx, f in enumerate(uploaded_files):
                status_text.text(f"Processing {f.name}... ({idx + 1}/{len(uploaded_files)})")
                
                # File size check
                file_size = f.size
                if file_size > MAX_FILE_SIZE:
                    st.warning(f"⚠️ {f.name} is very large ({file_size/1024/1024:.1f}MB). Processing may be slow.")
                
                try:
                    raw = f.read().decode("utf-8", errors="replace")
                    
                    # Malformed HTML check
                    if not raw or len(raw) < 10:
                        st.error(f"❌ {f.name}: File is empty or too short")
                        continue
                    
                    before_stats = analyze_issues(raw, pick_parser() if selected_parser is None else selected_parser)
                    
                    fixed, after_stats, used_parser = fix_html_content(
                        raw,
                        remove_empty=remove_empty_opt,
                        unwrap_block_wrapped_p=unwrap_block_opt,
                        prettify=prettify_opt,
                        parser=selected_parser,
                        strip_document_wrapper=strip_wrapper_opt
                    )
                    
                    # Check for errors
                    if "error" in after_stats:
                        st.error(f"❌ {f.name}: {after_stats['error']}")
                        continue
                    
                    all_stats.append(after_stats)
                    
                    # Validation
                    validation = validate_html(fixed, used_parser) if show_validation else None

                    with st.expander(f"📄 {f.name}  •  Parser: `{used_parser}`  •  Size: {file_size/1024:.1f}KB", expanded=False):
                        # Summary metrics
                        metric_cols = st.columns(4)
                        with metric_cols[0]:
                            st.metric("Nested <p> Fixed", after_stats.get('nested_p_fixed', 0))
                        with metric_cols[1]:
                            st.metric("Empty <p> Removed", after_stats.get('empty_p_removed', 0))
                        with metric_cols[2]:
                            st.metric("Blocks Unwrapped", after_stats.get('block_wraps_unwrapped', 0))
                        with metric_cols[3]:
                            st.metric("Comments Extracted", after_stats.get('comments_extracted_from_p', 0))
                        
                        # Validation results
                        if show_validation and validation:
                            if validation['valid']:
                                st.success("✅ Validation passed: " + ", ".join(validation['issues']))
                            else:
                                st.error("❌ Validation failed: " + ", ".join(validation['issues']))
                        
                        # Before/After comparison
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("**📥 Before – Issues**")
                            st.json(before_stats)
                            if len(raw) > FULL_DISPLAY_THRESHOLD:
                                st.code(raw[:PREVIEW_LENGTH] + "\n\n... (preview truncated) ...", language="html")
                                with st.expander("View full original"):
                                    st.code(raw, language="html")
                            else:
                                st.code(raw, language="html")
                        
                        with c2:
                            st.markdown("**📤 After – Fix Stats**")
                            st.json(after_stats)
                            if len(fixed) > FULL_DISPLAY_THRESHOLD:
                                st.code(fixed[:PREVIEW_LENGTH] + "\n\n... (preview truncated) ...", language="html")
                                with st.expander("View full fixed"):
                                    st.code(fixed, language="html")
                            else:
                                st.code(fixed, language="html")
                        
                        # Diff view
                        if show_diff:
                            st.markdown("**🔍 Changes (Diff)**")
                            diff_result = generate_diff(raw, fixed)
                            st.code(diff_result, language="diff")

                        st.download_button(
                            label="📥 Download fixed file",
                            data=fixed,
                            file_name=f"{f.name.rsplit('.',1)[0]}__fixed.html",
                            mime="text/html",
                            use_container_width=True,
                            key=f"download_{idx}"
                        )
                
                except Exception as e:
                    st.error(f"❌ Error processing {f.name}: {str(e)}")
                
                # Update progress
                progress_bar.progress((idx + 1) / len(uploaded_files))
            
            status_text.text("✅ All files processed!")
            
            # Overall statistics dashboard
            if all_stats:
                st.markdown("---")
                st.markdown("### 📈 Overall Statistics")
                dash_cols = st.columns(5)
                
                with dash_cols[0]:
                    st.metric("Files Processed", len(all_stats))
                with dash_cols[1]:
                    total_nested = sum(s.get('nested_p_fixed', 0) for s in all_stats)
                    st.metric("Total Nested <p> Fixed", total_nested)
                with dash_cols[2]:
                    total_empty = sum(s.get('empty_p_removed', 0) for s in all_stats)
                    st.metric("Total Empty <p> Removed", total_empty)
                with dash_cols[3]:
                    total_blocks = sum(s.get('empty_wp_blocks_removed', 0) for s in all_stats)
                    st.metric("Total WP Blocks Removed", total_blocks)
                with dash_cols[4]:
                    total_extracted = sum(s.get('comments_extracted_from_p', 0) for s in all_stats)
                    st.metric("Comments Extracted", total_extracted)

        # Single text input
        elif input_html and input_html.strip():
            try:
                # Malformed HTML check
                if len(input_html) < 10:
                    st.warning("⚠️ HTML seems too short - might be incomplete")
                
                before_stats = analyze_issues(input_html, pick_parser() if selected_parser is None else selected_parser)
                
                if "error" in before_stats:
                    st.error(f"❌ Error analyzing HTML: {before_stats['error']}")
                else:
                    fixed_html, after_stats, used_parser = fix_html_content(
                        input_html,
                        remove_empty=remove_empty_opt,
                        unwrap_block_wrapped_p=unwrap_block_opt,
                        prettify=prettify_opt,
                        parser=selected_parser,
                        strip_document_wrapper=strip_wrapper_opt
                    )
                    
                    # Check for errors
                    if "error" in after_stats:
                        st.error(f"❌ {after_stats['error']}")
                    elif "warning" in after_stats:
                        st.warning(f"⚠️ {after_stats['warning']}")
                    else:
                        # Success message with metrics
                        empty_span_cleanup = after_stats.get('final_cleanup_empty_span', 0)
                        comment_pairs_cleanup = after_stats.get('final_cleanup_comment_pairs', 0)
                        
                        success_msg = (
                            f"✅ **Fixed successfully!** • "
                            f"Nested `<p>`: **{after_stats['nested_p_fixed']}** • "
                            f"Unwrapped blocks: **{after_stats['block_wraps_unwrapped']}** • "
                            f"Empty `<p>`: **{after_stats['empty_p_removed']}** • "
                            f"WP-comment-only `<p>`: **{after_stats['wp_comment_wrapper_removed']}** • "
                            f"Empty WP blocks: **{after_stats['empty_wp_blocks_removed']}** • "
                            f"Comments extracted: **{after_stats['comments_extracted_from_p']}**"
                        )
                        
                        # Add final cleanup stats if any
                        cleanup_parts = []
                        if empty_span_cleanup > 0:
                            cleanup_parts.append(f"**{empty_span_cleanup}** `<p><span></span></p>`")
                        if comment_pairs_cleanup > 0:
                            cleanup_parts.append(f"**{comment_pairs_cleanup}** comment pairs")
                        
                        if cleanup_parts:
                            success_msg += f" • Final cleanup: {' + '.join(cleanup_parts)} removed"
                        
                        success_msg += f" • Parser: `{used_parser}` • Passes: {after_stats['iterations']}"
                        
                        st.success(success_msg)
                        
                        # Validation
                        if show_validation:
                            validation = validate_html(fixed_html, used_parser)
                            if validation['valid']:
                                st.success("✅ Validation: " + ", ".join(validation['issues']))
                            else:
                                st.error("❌ Validation: " + ", ".join(validation['issues']))
                        
                        st.markdown("---")
                        
                        # Metrics dashboard
                        metric_cols = st.columns(5)
                        with metric_cols[0]:
                            st.metric("Before: Nested <p>", before_stats.get('nested_p', 0))
                        with metric_cols[1]:
                            st.metric("Before: Empty <p>", before_stats.get('empty_p', 0))
                        with metric_cols[2]:
                            st.metric("Before: <p> with <span>", before_stats.get('empty_p_with_span', 0))
                        with metric_cols[3]:
                            st.metric("Before: Block wraps", before_stats.get('p_wrapping_blocks', 0))
                        with metric_cols[4]:
                            st.metric("Before: Comments in <p>", before_stats.get('wp_comments_in_p', 0))
                        
                        st.markdown("---")
                        st.markdown("**📤 Output (Gutenberg-safe fragment):**")
                        
                        if len(fixed_html) > FULL_DISPLAY_THRESHOLD:
                            st.code(fixed_html[:PREVIEW_LENGTH] + "\n\n... (preview truncated) ...", language="html")
                            with st.expander("📖 View full output", expanded=False):
                                st.code(fixed_html, language="html")
                        else:
                            st.code(fixed_html, language="html")
                        
                        # Diff view
                        if show_diff:
                            st.markdown("---")
                            st.markdown("**🔍 Changes (Diff)**")
                            diff_result = generate_diff(input_html, fixed_html)
                            st.code(diff_result, language="diff")

                        st.download_button(
                            label="📥 Download Fixed HTML",
                            data=fixed_html,
                            file_name="fixed_wordpress_content.html",
                            mime="text/html",
                            use_container_width=True
                        )
            
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")
        
        else:
            st.info("📌 Paste HTML or upload files, then click **Fix HTML**.")
    else:
        st.info("👈 Paste HTML or upload files, adjust settings, and click **Fix HTML**.")

# Footer
st.markdown("---")
st.caption(
    "🔧 Enhanced WordPress HTML Content Fixer v2.3 • "
    "Preserves Gutenberg comments (with proper spacing!), extracts comments from inside `<p>` tags, removes nested/empty/bridge `<p>`, "
    "unwraps invalid structures, strips document wrapper, deletes empty Gutenberg blocks, "
    "**and performs final regex cleanup of `<p><span></span></p>` tags and consecutive comment pairs**. • "
    "Now with validation, presets, and comprehensive statistics."
)
