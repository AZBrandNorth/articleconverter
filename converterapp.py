import streamlit as st

# ---- Imports with graceful fallbacks ----
PARSER_ORDER = []
try:
    from bs4 import BeautifulSoup, NavigableString, Tag
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

# ---- App guardrail if bs4 missing ----
if not BS4_AVAILABLE:
    st.set_page_config(page_title="HTML Content Fixer", page_icon="🔧", layout="wide")
    st.error(
        "⚠️ **Missing Required Package: beautifulsoup4**\n\n"
        "**For Streamlit Cloud:**\n"
        "1) Ensure `requirements.txt` contains `beautifulsoup4==4.12.3`\n"
        "2) Also add: `lxml==5.3.0` and `html5lib==1.1`\n"
        "3) Reboot the app\n\n"
        "**Local:** `pip install beautifulsoup4 lxml html5lib`"
    )
    st.stop()

# ----------------- Utilities -----------------
BLOCK_LEVEL_TAGS = {
    # HTML5 block-ish elements frequently wrapped by P in broken markup
    "div", "section", "article", "aside", "header", "footer", "main", "nav",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "figure", "figcaption",
    "blockquote", "pre", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6"
}

NON_EMPTY_INLINE_OK = {"img", "br", "svg", "iframe", "video", "audio", "canvas", "embed", "object"}

def pick_parser() -> str:
    # Prefer the most robust parsers available
    return PARSER_ORDER[0] if PARSER_ORDER else "html.parser"

def is_effectively_empty(tag: Tag) -> bool:
    """True if <p> has no visible text and no meaningful inline content."""
    # Allow some inline media to count as content
    for child in tag.children:
        if isinstance(child, Tag) and child.name in NON_EMPTY_INLINE_OK:
            return False
        if isinstance(child, NavigableString) and child.strip():
            # Has visible text
            return False
    # No visible text. Check if text reduces to only &nbsp; or whitespace.
    text = tag.get_text(separator="", strip=True)
    text = text.replace("\xa0", "").replace("&nbsp;", "").strip()
    return text == ""

def unwrap_children(tag: Tag, child_name: str):
    """Unwrap specific nested children of a tag (used for nested <p>)."""
    changed = 0
    nested = tag.find_all(child_name, recursive=True)
    for n in nested:
        if n is not tag:
            n.unwrap()
            changed += 1
    return changed

def unwrap_p_around_block(tag: Tag):
    """
    If a <p> wraps block-level tags, unwrap the <p> entirely.
    """
    for c in tag.children:
        if isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS:
            tag.unwrap()
            return 1
    return 0

def normalize_paragraphs(soup: BeautifulSoup, remove_empty: bool, unwrap_block_wrapped_p: bool):
    """
    Recursively:
      - Unwrap nested <p> inside <p>
      - Optionally remove empty <p>
      - Optionally unwrap <p> that wrap block-level elements
    Continues until stable (no more changes).
    """
    total_nested_fixes = 0
    total_empty_removed = 0
    total_unwrapped_block = 0

    changed = True
    safety_counter = 0

    while changed and safety_counter < 50:
        changed = False
        safety_counter += 1

        # Work on a snapshot list because we may be mutating
        p_tags = list(soup.find_all("p"))
        for p in p_tags:
            # 1) Fix nested <p> (deep)
            nested_count = unwrap_children(p, "p")
            if nested_count:
                total_nested_fixes += nested_count
                changed = True

            # As unwrapping may have changed children, optionally unwrap block-level wraps
            if unwrap_block_wrapped_p and p.parent:
                unwrapped = unwrap_p_around_block(p)
                if unwrapped:
                    total_unwrapped_block += unwrapped
                    changed = True
                    # p is gone now; skip further checks
                    continue

            # 2) Optionally remove empty <p>
            if remove_empty and p and p.name == "p" and is_effectively_empty(p):
                p.decompose()
                total_empty_removed += 1
                changed = True

    return {
        "nested_p_fixed": total_nested_fixes,
        "empty_p_removed": total_empty_removed,
        "block_wraps_unwrapped": total_unwrapped_block,
        "iterations": safety_counter
    }

def analyze_issues(html: str, parser: str):
    soup = BeautifulSoup(html, parser)
    nested = 0
    block_wraps = 0
    empties = 0

    for p in soup.find_all("p"):
        # nested
        nested += len(p.find_all("p"))
        # block-level wrap
        if any(isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS for c in p.children):
            block_wraps += 1
        # empties
        if is_effectively_empty(p):
            empties += 1

    return {"nested_p": nested, "p_wrapping_blocks": block_wraps, "empty_p": empties}

def fix_html_content(html: str, remove_empty=True, unwrap_block_wrapped_p=True, prettify=False, parser=None):
    """Main fix function; robust & idempotent."""
    parser = parser or pick_parser()
    soup = BeautifulSoup(html, parser)
    stats = normalize_paragraphs(soup, remove_empty=remove_empty, unwrap_block_wrapped_p=unwrap_block_wrapped_p)
    fixed = soup.prettify() if prettify else str(soup)
    return fixed, stats, parser

# ----------------- Streamlit UI -----------------
st.set_page_config(page_title="HTML Content Fixer", page_icon="🔧", layout="wide")
st.title("WordPress HTML Content Fixer")
st.markdown("Remove **nested `<p>` tags**, optionally strip **empty paragraphs**, and fix `<p>` wrapping **block-level elements** (a frequent cause of the WP *“unexpected/invalid content”* error).")

with st.expander("📦 System Status"):
    st.write("**Parsers (best → fallback):**", ", ".join(PARSER_ORDER))
    st.success("✅ BeautifulSoup available") if BS4_AVAILABLE else st.error("❌ beautifulsoup4 missing")
    st.info("Tip: Having **html5lib** installed yields the most browser-like parsing.")

# Options
st.sidebar.header("Settings")
remove_empty_opt = st.sidebar.checkbox("Remove empty paragraphs", value=True,
                                      help="Deletes <p> that contain only whitespace or &nbsp;.")
unwrap_block_opt = st.sidebar.checkbox("Unwrap <p> that wrap block-level elements", value=True,
                                       help="If a <p> improperly wraps elements like <div>, <ul>, <table>, etc., unwrap it.")
prettify_opt = st.sidebar.checkbox("Prettify output (formatted)", value=False,
                                   help="Prettify adds indentation/newlines. Turn off for compact HTML.")
parser_choice = st.sidebar.selectbox("Parser to use", options=["auto"] + PARSER_ORDER, index=0,
                                     help="Choose a specific parser or let the app pick the best available.")

col1, col2 = st.columns([1, 1])

# -------- Left: Input (text & files) --------
with col1:
    st.subheader("Input HTML")
    input_html = st.text_area("Paste your HTML:", height=320, placeholder="Paste WordPress HTML content here…")

    uploaded_files = st.file_uploader(
        "…or upload one or more .html/.htm files",
        type=["html", "htm", "txt"],
        accept_multiple_files=True
    )

    run_btn = st.button("Fix HTML", type="primary", use_container_width=True)

# -------- Right: Output --------
with col2:
    st.subheader("Fixed HTML")

    if run_btn:
        # Choose parser
        parser = None if parser_choice == "auto" else parser_choice

        # Case A: Batch files
        if uploaded_files:
            st.markdown("### Batch Results")
            for f in uploaded_files:
                raw = f.read().decode("utf-8", errors="replace")
                before_stats = analyze_issues(raw, pick_parser() if parser is None else parser)
                fixed, after_stats, used_parser = fix_html_content(
                    raw, remove_empty=remove_empty_opt, unwrap_block_wrapped_p=unwrap_block_opt,
                    prettify=prettify_opt, parser=parser
                )

                with st.expander(f"📄 {f.name}  •  Parser: `{used_parser}`", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Before – Issues**")
                        st.json(before_stats)
                        st.code(raw[:10000] if len(raw) > 10000 else raw, language="html")
                    with c2:
                        st.markdown("**After – Fix Stats**")
                        st.json(after_stats)
                        st.code(fixed[:10000] if len(fixed) > 10000 else fixed, language="html")

                    st.download_button(
                        label="Download fixed file",
                        data=fixed,
                        file_name=f"{f.name.rsplit('.',1)[0]}__fixed.html",
                        mime="text/html",
                        use_container_width=True
                    )

        # Case B: Single text input
        elif input_html.strip():
            before_stats = analyze_issues(input_html, pick_parser() if parser is None else parser)
            fixed_html, after_stats, used_parser = fix_html_content(
                input_html,
                remove_empty=remove_empty_opt,
                unwrap_block_wrapped_p=unwrap_block_opt,
                prettify=prettify_opt,
                parser=parser
            )

            if before_stats["nested_p"] or before_stats["p_wrapping_blocks"]:
                st.warning(
                    f"Fixed nested `<p>`: **{after_stats['nested_p_fixed']}** • "
                    f"Unwrapped `<p>` around blocks: **{after_stats['block_wraps_unwrapped']}** • "
                    f"Removed empty `<p>`: **{after_stats['empty_p_removed']}** • "
                    f"Parser: `{used_parser}` • Passes: {after_stats['iterations']}"
                )
            else:
                st.success(f"No nested `<p>` found. Parser: `{used_parser}`")

            st.markdown("---")
            ex_before = '<p><span><p>content here</p></span></p>'
            ex_after  = '<p><span>content here</span></p>'
            with st.expander("Example Fix", expanded=False):
                cb, ca = st.columns(2)
                with cb:
                    st.markdown("**Before:**")
                    st.code(ex_before, language="html")
                with ca:
                    st.markdown("**After:**")
                    st.code(ex_after, language="html")

            st.markdown("---")
            st.markdown("**Output:**")
            st.code(fixed_html, language="html")

            st.download_button(
                label="Download Fixed HTML",
                data=fixed_html,
                file_name="fixed_wordpress_content.html",
                mime="text/html",
                use_container_width=True
            )
        else:
            st.info("Paste HTML or upload files, then click **Fix HTML**.")
    else:
        st.info("Paste HTML or upload files, adjust settings in the sidebar, and click **Fix HTML**.")

st.markdown("---")
st.caption("This tool recursively removes nested `<p>` tags, optionally removes empty `<p>`, and unwraps `<p>` that wrap block-level elements to reduce WordPress block errors.")
