"""Build the self-contained index.html (single document the preview can't cache stale).

Sources:
  app/static/index.template.html  — page structure with __APP_CSS__ / __APP_JS__ placeholders
  app/static/styles.css           — inlined into <style>
  app/static/app.js               — inlined into <script>
Output:
  app/static/index.html           — the self-contained page the server serves

Run:  python3 scripts/inline_app.py
The template is the source of truth for HTML structure and is never modified.
"""
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "app" / "static"
tpl = (base / "index.template.html").read_text()
css = (base / "styles.css").read_text()
js = (base / "app.js").read_text()

assert "__APP_CSS__" in tpl and "__APP_JS__" in tpl, "placeholders missing from index.template.html"
assert "</script>" not in js.lower(), "JS contains a closing script tag — would break inlining"
assert "</style>" not in css.lower(), "CSS contains a closing style tag — would break inlining"

out = tpl.replace("__APP_CSS__", css).replace("__APP_JS__", js)
(base / "index.html").write_text(out)
print(f"inlined index.html: {len(out)} bytes")
