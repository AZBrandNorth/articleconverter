#!/usr/bin/env python3
# clean_wp_html.py
# Remove Gutenberg comments and &nbsp;-only paragraphs so WP stops creating empty blocks.
# Usage:
#   pip install beautifulsoup4 lxml html5lib
#   python clean_wp_html.py input.html -o output.html
#   # or:
#   cat input.html | python clean_wp_html.py > output.html

from __future__ import annotations
import sys, re, argparse
from typing import Dict
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

NBSP = "\xa0"
BLOCK_LEVEL = {
    "address","article","aside","blockquote","canvas","dd","div","dl","dt","fieldset",
    "figcaption","figure","footer","form","h1","h2","h3","h4","h5","h6","header",
    "hr","li","main","nav","noscript","ol","p","pre","section","table","tfoot","ul",
    "video","iframe","picture"
}

def pick_parser() -> str:
    try:
        import lxml  # noqa
        return "lxml"
    except Exception:
        try:
            import html5lib  # noqa
            return "html5lib"
        except Exception:
            return "html.parser"

def is_blank_text(s: str) -> bool:
    return s.replace(NBSP, " ").strip() == ""

def is_wp_comment_text(text: str) -> bool:
    t = (text or "").strip().replace(" ", "")
    # matches <!-- wp:paragraph -->, <!-- /wp:paragraph -->, etc.
    return t.startswith("wp:") or t.startswith("/wp:")

def strip_all_wp_comments(soup: BeautifulSoup) -> int:
    removed = 0
    for c in list(soup.find_all(string=lambda x: isinstance(x, Comment))):
        if is_wp_comment_text(str(c)):
            c.extract()
            removed += 1
    return removed

def p_is_only_wp_comments_and_breaks(p: Tag) -> bool:
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Comment):
            if not is_wp_comment_text(str(child)):
                return False
        elif isinstance(child, Tag) and child.name == "br":
            continue
        else:
            return False
    return True

def p_is_truly_empty(p: Tag) -> bool:
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Tag) and child.name == "br":
            continue
        elif isinstance(child, Comment):
            # treat any non-wp comment as content
            return False
        else:
            return False
    return True

def p_wraps_block_elements_only(p: Tag) -> bool:
    has_block = False
    for child in p.contents:
        if isinstance(child, NavigableString):
            if not is_blank_text(str(child)):
                return False
        elif isinstance(child, Comment):
            if not is_wp_comment_text(str(child)):
                return False
        elif isinstance(child, Tag):
            if child.name == "br":
                continue
            if child.name in BLOCK_LEVEL:
                has_block = True
            else:
                return False
        else:
            return False
    return has_block

def remove_empty_wp_blocks(soup: BeautifulSoup) -> int:
    removed = 0
    for tag in list(soup.find_all(True)):
        classes = tag.get("class") or []
        if any(cls.startswith("wp-block-") for cls in classes):
            text_ok = is_blank_text(tag.get_text(""))
            has_non_ws = any(isinstance(c, Tag) and c.name not in {"br"} for c in tag.contents)
            if text_ok and not has_non_ws:
                tag.decompose()
                removed += 1
    return removed

def normalize_paragraphs(soup: BeautifulSoup, unwrap_block_wrapped_p: bool) -> Dict[str,int]:
    stats = {"p_wp_comment_only_removed":0, "p_empty_removed":0, "p_unwrapped_blockwrap":0}
    for p in list(soup.find_all("p")):
        if p_is_only_wp_comments_and_breaks(p):
            p.decompose(); stats["p_wp_comment_only_removed"] += 1; continue
        if p_is_truly_empty(p):
            p.decompose(); stats["p_empty_removed"] += 1; continue
        if unwrap_block_wrapped_p and p_wraps_block_elements_only(p):
            p.unwrap(); stats["p_unwrapped_blockwrap"] += 1
    return stats

def clean_wp_html(html: str, unwrap_block_wrapped_p: bool = True) -> str:
    soup = BeautifulSoup(html, pick_parser())

    # First pass: remove &nbsp;/comment-only <p> and empty <p>
    normalize_paragraphs(soup, unwrap_block_wrapped_p=unwrap_block_wrapped_p)

    # Remove Gutenberg comments anywhere
    strip_all_wp_comments(soup)

    # Remove empty Gutenberg block containers (if any)
    remove_empty_wp_blocks(soup)

    # Serialize and tighten up stray whitespace between tags
    target = soup.body or soup
    out = target.decode()
    out = re.sub(r">\s+<", "><", out)          # collapse inter-tag whitespace
    out = re.sub(r"(\n\s*){2,}", "\n", out)    # collapse multiple blank lines
    return out

# ---------------- CLI ----------------
def main():
    ap = argparse.ArgumentParser(description="Clean WordPress Gutenberg HTML (remove block comments and &nbsp;-only paragraphs).")
    ap.add_argument("infile", nargs="?", help="Input HTML file (defaults to STDIN)")
    ap.add_argument("-o", "--out", help="Output file (defaults to STDOUT)")
    ap.add_argument("--no-unwrap", action="store_true", help="Do not unwrap <p> that only wrap block elements")
    args = ap.parse_args()

    data = sys.stdin.read() if not args.infile else open(args.infile, "r", encoding="utf-8").read()
    cleaned = clean_wp_html(data, unwrap_block_wrapped_p=not args.no_unwrap)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(cleaned)
    else:
        sys.stdout.write(cleaned)

if __name__ == "__main__":
    main()
