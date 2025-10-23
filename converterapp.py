# app.py
# WordPress HTML Content Fixer
# - Removes nested <p>, optional empty <p>, and <p> wrapping block elements
# - Preserves Gutenberg block comments, strips document wrapper
# - Removes empty Gutenberg blocks (<!-- wp:* --> ... <!-- /wp:* -->)

import streamlit as st

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

# ---------------- App ----------------
st.set_page_config(page_title="HTML Content Fixer", page_icon="🔧", layout="wide")

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
NON_EMPTY_INLINE_OK = {"img", "br", "svg", "iframe", "video", "audio", "canvas", "embed", "object"}

def pick_parser() -> str:
    return PARSER_ORDER[0] if PARSER_ORDER else "html.parser"

def is_effectively_empty(tag: Tag) -> bool:
    """True if <p> has no visible text and no meaningful inline content."""
    for child in tag.children:
        if isinstance(child, Tag) and child.name in NON_EMPTY_INLINE_OK:
            return False
        if isinstance(child, NavigableString) and child.strip():
            return False
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

def normalize_paragraphs(soup: BeautifulSoup, remove_empty: bool, unwrap_block_wrapped_p: bool):
    """
    Recursively:
      - Unwrap nested <p> inside <p>
      - Optionally remove empty <p>
      - Optionally unwrap <p> that wrap block-level elements
    """
    total_nested_fixes = 0
    total_empty_removed = 0
    total_unwrapped_block = 0
    changed = True
    safety_counter = 0

    while changed and safety_counter < 50:
        changed = False
        safety_counter += 1
        p_tags = list(soup.find_all("p"))
        for p in p_tags:
            nested_count = unwrap_children(p, "p")
            if nested_count:
                total_nested_fixes += nested_count
                changed = True

            if unwrap_block_wrapped_p and p.parent:
                unwrapped = unwrap_p_around_block(p)
                if unwrapped:
                    total_unwrapped_block += unwrapped
                    changed = True
                    continue  # p was unwrapped; don't touch further

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
    """
    Remove empty Gutenberg blocks:
      <!-- wp:paragraph -->
      [only whitespace/empty nodes]
      <!-- /wp:paragraph -->
    """
    container = soup.body if getattr(soup, "body", None) else soup
    removed = 0
    i = 0
    nodes = list(container.children)

    while i < len(nodes):
        n = nodes[i]
        if isinstance(n, Comment) and str(n).strip().startswith("wp:"):
            # find matching closing comment
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
                # delete i..j inclusive
                for k in range(i, j + 1):
                    try:
                        nodes[k].extract()
                    except Exception:
                        pass
                removed += 1
                nodes = list(container.children)  # refresh view
                continue
        i += 1
    return removed

def analyze_issues(html: str, parser: str):
    soup = BeautifulSoup(html, parser)
    nested = 0
    block_wraps = 0
    empties = 0
    for p in soup.find_all("p"):
        nested += len(p.find_all("p"))
        if any(isinstance(c, Tag) and c.name in BLOCK_LEVEL_TAGS for c in p.children):
            block_wraps += 1
        if is_effectively_empty(p):
            empties += 1
    return {"nested_p": nested, "p_wrapping_blocks": block_wraps, "empty_p": empties}

def serialize_fragment(soup: BeautifulSoup, strip_document_wrapper: bool = True, prettify: bool = False) -> str:
    """
    Return HTML suitable for Gutenberg:
    - If body exists and strip_document_wrapper=True → join body children (preserve comments as <!-- ... -->).
    """
    def to_html(node) -> str:
        if isinstance(node, Comment):
            return f"<!-- {node} -->"  # BeautifulSoup loses the delimiters if we don't add them
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
):
    """Main fix function."""
    parser = parser or pick_parser()
    soup = BeautifulSoup(html, parser)

    stats = normalize_paragraphs(
        soup,
        remove_empty=remove_empty,
        unwrap_block_wrapped_p=unwrap_block_wrapped_p
    )

    # Remove empty Gutenberg blocks created or exposed by cleanup
    stats["empty_wp_blocks_removed"] = remove_empty_gutenberg_blocks(soup)

    fixed = serialize_fragment(
        soup,
        strip_document_wrapper=strip_document_wrapper,
        prettify=prettify
    )
    return fixed, stats, parser

# ---------------- UI ----------------
st.title("WordPress HTML Content Fixer")
st.markdown(
    "Fix nested `<p>` tags, optionally remove empty `<p>`, unwrap `<p>` around block elements, "
    "and output a **Gutenberg-safe fragment** (preserves block comments, no `<html>/<body>`). "
    "Now also removes **empty Gutenberg blocks**."
)

with st.expander("📦 System Status", expanded=False):
    st.write("**Parsers (best → fallback):**", ", ".join(PARSER_ORDER))
    st.success("✅ BeautifulSoup available")

# Sidebar options
st.sidebar.header("Settings")
remove_empty_opt = st.sidebar.checkbox("Remove empty paragraphs", value=True)
unwrap_block_opt = st.sidebar.checkbox("Unwrap <p> that wrap block elements", value=True)
prettify_opt = st.sidebar.checkbox("Prettify output (formatted)", value=False)
strip_wrapper_opt = st.sidebar.checkbox("Strip <html>/<body> wrapper (recommended)", value=True)
parser_choice = st.sidebar.selectbox("Parser to use", options=["auto"] + PARSER_ORDER, index=0)

col1, col2 = st.columns([1, 1])

# -------- Left: Input --------
with col1:
    st.subheader("Input HTML")
    input_html = st.text_area("Paste your HTML:", height=320, placeholder="Paste WordPress HTML content here…")

    uploaded_files = st.file_uploader(
        "…or upload .html/.htm/.txt files",
        type=["html", "htm", "txt"],
        accept_multiple_files=True
    )

    run_btn = st.button("Fix HTML", type="primary", use_container_width=True)

# -------- Right: Output --------
with col2:
    st.subheader("Fixed HTML")

    if run_btn:
        selected_parser = None if parser_choice == "auto" else parser_choice

        # Batch files
        if uploaded_files:
            st.markdown("### Batch Results")
            for f in uploaded_files:
                raw = f.read().decode("utf-8", errors="replace")
                before_stats = analyze_issues(raw, pick_parser() if selected_parser is None else selected_parser)
                fixed, after_stats, used_parser = fix_html_content(
                    raw,
                    remove_empty=remove_empty_opt,
                    unwrap_block_wrapped_p=unwrap_block_opt,
                    prettify=prettify_opt,
                    parser=selected_parser,
                    strip_document_wrapper=strip_wrapper_opt
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

        # Single text input
        elif input_html and input_html.strip():
            before_stats = analyze_issues(input_html, pick_parser() if selected_parser is None else selected_parser)
            fixed_html, after_stats, used_parser = fix_html_content(
                input_html,
                remove_empty=remove_empty_opt,
                unwrap_block_wrapped_p=unwrap_block_opt,
                prettify=prettify_opt,
                parser=selected_parser,
                strip_document_wrapper=strip_wrapper_opt
            )

            st.success(
                f"Fixed nested `<p>`: **{after_stats['nested_p_fixed']}** • "
                f"Unwrapped `<p>` around blocks: **{after_stats['block_wraps_unwrapped']}** • "
                f"Removed empty `<p>`: **{after_stats['empty_p_removed']}** • "
                f"Removed empty Gutenberg blocks: **{after_stats['empty_wp_blocks_removed']}** • "
                f"Parser: `{used_parser}` • Passes: {after_stats['iterations']}"
            )

            st.markdown("---")
            st.markdown("**Output (Gutenberg-safe fragment):**")
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
        st.info("Paste HTML or upload files, adjust settings, and click **Fix HTML**.")

st.markdown("---")
st.caption("Preserves Gutenberg comments, removes nested/empty <p>, unwraps invalid structures, strips document wrapper, and deletes empty Gutenberg blocks.")
