# app.py
# HTML cleaner for WordPress Gutenberg pastes
# - Strips ALL Gutenberg comments (wp:..., /wp:...)
# - Deletes <p> that only contain those comments (with or without stray <br>)
# - Deletes truly-empty <p> (whitespace, &nbsp;, <br>)
# - Optionally unwraps <p> that incorrectly wrap block-level elements
# - Leaves you with plain, block-friendly HTML (no empty bridges)

from __future__ import annotations

import re
from typing import Dict, Tuple

import streamlit as st
from bs4 import BeautifulSoup, NavigableString, Tag, Comment

# ----------------------------
# Parser selection
# ----------------------------
def pick_parser() -> str:
    # Prefer robust parsers if installed
    try:
        import lxml  # noqa: F401
        return "lxml"
    except Exception:
        try:
            import html5lib  # noqa: F401
            return "html5lib"
        except Exception:
            return "html.parser"

# ----------------------------
# Helpers
# ----------------------------
NBSP = "\xa0"

BLOCK_LEVEL = {
    "address","article","aside","blockquote","canvas","dd","div","dl","dt","fieldset",
    "figcaption","figure","footer","form","h1","h2","h3","h4","h5","h6","header",
    "hr","li","main","nav","noscript","ol","p","pre","section","table","tfoot","ul",
    "video","iframe","picture"
}

def is_blank_text(s: str) -> bool:
    return s.replace(NBSP, " ").strip() == ""

def is_wp_comment_text(text: str) -> bool:
    """
    Accepts sloppy variants like: '  wp:paragraph  ' or '  /wp:paragraph  '
    """
    t = text.strip()
    # remove internal spaces so <!--  wp:paragraph  --> is caught
    t_compact = t.replace(" ", "")
    return t_compact.startswith("wp:") or t_compact.startswith("/wp:")

def is_wp_comment(node) -> bool:
    return isinstance(node, Comment) and is_wp_comment_text(str(node))

def strip_all_wp_comments(soup: BeautifulSoup) -> int:
    """
    Remove ALL Gutenberg block comments anywhere in the tree.
    """
    removed = 0
    for c in list(soup.find_all(string=lambda x: isinstance(x, Comment))):
        if is_wp_comment(c):
            c.extract()
            removed += 1
    return removed

def p_is_only_wp_comments_and_breaks(p: Tag) -> bool:
    """
    True if <p> contains only WP comments, optional <br>, and whitespace.
    """
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Comment):
            if not is_wp_comment(child):
                return False
        elif isinstance(child, Tag) and child.name == "br":
            continue
        else:
            return False
    return True

def p_is_truly_empty(p: Tag) -> bool:
    """
    True if <p> has only whitespace/&nbsp;/<br>.
    """
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Tag) and child.name == "br":
            continue
        elif isinstance(child, Comment):
            # non-wp comments still count as content, so keep
            return False
        else:
            return False
    return True

def p_wraps_block_elements_only(p: Tag) -> bool:
    """
    True if <p> incorrectly wraps (one or more) block-level elements and nothing else,
    except whitespace, &nbsp;, <br>, or WP comments.
    """
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Comment):
            if not is_wp_comment(child):
                # other comments mean: keep p
                return False
        elif isinstance(child, Tag):
            if child.name == "br":
                # ignore stray <br>
                continue
            if child.name not in BLOCK_LEVEL:
                # inline content mixed in → don't unwrap
                return False
        else:
            return False
    # At least one block present?
    return any(isinstance(c, Tag) and c.name in BLOCK_LEVEL for c in p.contents)

def unwrap_paragraph(p: Tag) -> None:
    # Replace <p> by its children
    p.unwrap()

def remove_empty_gutenberg_blocks(soup: BeautifulSoup) -> int:
    """
    Remove empty Gutenberg block containers, e.g. <div class="wp-block-..."></div>
    """
    removed = 0
    for tag in list(soup.find_all(True)):
        classes = tag.get("class") or []
        if any(cls.startswith("wp-block-") for cls in classes):
            # consider empty if no text (after stripping nbsp) and no non-whitespace elements
            text_ok = is_blank_text(tag.get_text(""))
            has_non_whitespace_children = any(
                isinstance(c, Tag) and c.name not in {"br"} for c in tag.contents
            )
            if text_ok and not has_non_whitespace_children:
                tag.decompose()
                removed += 1
    return removed

def serialize_fragment(
    soup: BeautifulSoup,
    strip_document_wrapper: bool = True,
    prettify: bool = False
) -> str:
    # Prefer body contents if present
    node = soup.body if strip_document_wrapper and soup.body else soup
    html = node.decode(formatter="html")
    if prettify:
        try:
            html = BeautifulSoup(html, pick_parser()).prettify()
        except Exception:
            pass
    return html

def normalize_paragraphs(
    soup: BeautifulSoup,
    remove_empty: bool = True,
    unwrap_block_wrapped_p: bool = True
) -> Dict[str, int]:
    stats = {
        "p_wp_comment_only_removed": 0,
        "p_empty_removed": 0,
        "p_unwrapped_blockwrap": 0,
    }

    for p in list(soup.find_all("p")):
        # 1) <p> that are just WP comments (even with <br>)
        if p_is_only_wp_comments_and_breaks(p):
            p.decompose()
            stats["p_wp_comment_only_removed"] += 1
            continue

        # 2) truly empty <p>
        if remove_empty and p_is_truly_empty(p):
            p.decompose()
            stats["p_empty_removed"] += 1
            continue

        # 3) <p> that wrap block elements only
        if unwrap_block_wrapped_p and p_wraps_block_elements_only(p):
            unwrap_paragraph(p)
            stats["p_unwrapped_blockwrap"] += 1

    return stats

# ----------------------------
# Cleaning pipeline
# ----------------------------
def fix_html_content(
    html: str,
    remove_empty: bool = True,
    unwrap_block_wrapped_p: bool = True,
    prettify: bool = False,
    parser: str | None = None,
    strip_document_wrapper: bool = True,
    strip_wp_comments: bool = True,
) -> Tuple[str, Dict[str, int], str]:
    parser = parser or pick_parser()
    soup = BeautifulSoup(html, parser)

    # Normalize paragraphs first (can remove many junk <p>)
    stats = normalize_paragraphs(
        soup,
        remove_empty=remove_empty,
        unwrap_block_wrapped_p=unwrap_block_wrapped_p,
    )

    # Strip ALL Gutenberg comments anywhere (prevents WP from turning them into visible text)
    stats["wp_comments_stripped"] = 0
    if strip_wp_comments:
        stats["wp_comments_stripped"] = strip_all_wp_comments(soup)

    # Remove empty Gutenberg block containers if any remain
    stats["empty_wp_blocks_removed"] = remove_empty_gutenberg_blocks(soup)

    fixed = serialize_fragment(
        soup,
        strip_document_wrapper=strip_document_wrapper,
        prettify=prettify
    )
    return fixed, stats, parser

# ----------------------------
# Streamlit UI
# ----------------------------
st.set_page_config(page_title="WP HTML Cleaner", page_icon="🧹", layout="wide")
st.title("🧹 WordPress Gutenberg HTML Cleaner")

st.write(
    "Paste your HTML on the left. Get clean, block-friendly HTML on the right. "
    "This removes Gutenberg block comments and empty bridge paragraphs."
)

col_in, col_out = st.columns(2)

with st.sidebar:
    st.header("Settings")
    remove_empty_opt = st.checkbox("Remove empty <p>", value=True)
    unwrap_block_opt = st.checkbox("Unwrap <p> around block elements", value=True)
    strip_wp_opt = st.checkbox("Strip Gutenberg comments (wp:*)", value=True)
    prettify_opt = st.checkbox("Prettify output", value=False)
    strip_wrapper_opt = st.checkbox("Strip <html>/<body> wrapper", value=True)

    st.caption(
        "Tip: keep **Strip Gutenberg comments** ON. "
        "Those are what cause `<p><!-- /wp:... --><br><!-- wp:... --></p>` stubs."
    )

with col_in:
    sample = """<!-- wp:paragraph -->
<p>Indiana stands as a recovery-friendly state with <b>over 300 addiction treatment facilities</b> ...</p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p><!--  /wp:paragraph  --><br><!--  wp:paragraph  --></p>
<!-- /wp:paragraph -->

<!-- wp:paragraph -->
<p>This comprehensive guide covers alcohol-free entertainment across Indiana's diverse landscape...</p>
<!-- /wp:paragraph -->"""
    input_html = st.text_area("Input HTML", sample, height=520)

parser_choice = st.selectbox(
    "Parser",
    options=["auto", "lxml", "html5lib", "html.parser"],
    index=0,
    help="auto = prefer lxml, then html5lib, else built-in html.parser"
)
selected_parser = None if parser_choice == "auto" else parser_choice

fixed_html, after_stats, used_parser = fix_html_content(
    input_html,
    remove_empty=remove_empty_opt,
    unwrap_block_wrapped_p=unwrap_block_opt,
    prettify=prettify_opt,
    parser=selected_parser,
    strip_document_wrapper=strip_wrapper_opt,
    strip_wp_comments=strip_wp_opt,
)

with col_out:
    st.subheader("Cleaned HTML")
    st.code(fixed_html, language="html")

st.success(
    f"Parser: {used_parser}  •  "
    f"Removed wp-comment-only <p>: {after_stats['p_wp_comment_only_removed']}  •  "
    f"Removed empty <p>: {after_stats['p_empty_removed']}  •  "
    f"Unwrapped block-wrapped <p>: {after_stats['p_unwrapped_blockwrap']}  •  "
    f"Stripped WP comments: {after_stats['wp_comments_stripped']}  •  "
    f"Removed empty Gutenberg containers: {after_stats['empty_wp_blocks_removed']}"
)

st.caption(
    "Now, when you paste this into the WP editor and click **Convert to blocks**, "
    "there will be no leftover `<p><!-- … --></p>` artifacts."
)
