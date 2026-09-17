"""Build the self-contained index.html (single document the preview can't cache stale).

Run:  python3 scripts/inline_app.py
Sources: app/static/{index.html, styles.css, app.js} — index.html holds the
__APP_CSS__ / __APP_JS__ placeholders; the build swaps them for the files.
"""
import sys
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "app" / "static"
html = (base / "index.html").read_text()
css = (base / "styles.css").read_text()
js = (base / "app.js").read_text()

assert "__APP_CSS__" in html and "__APP_JS__" in html, "placeholders missing from index.html"
assert "</script>" not in js.lower(), "JS contains a closing script tag — would break inlining"
assert "</style>" not in css.lower(), "CSS contains a closing style tag — would break inlining"

html = html.replace("__APP_CSS__", css).replace("__APP_JS__", js)
(base / "index.html").write_text(html)
print(f"inlined index.html: {len(html)} bytes")
