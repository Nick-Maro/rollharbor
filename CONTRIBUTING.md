# Contributing

Start with a concrete problem at a table. Small fixes to usability, accessibility,
Italian text, rule references and save reliability are particularly helpful.
Discuss broad rules-engine or remote-hosting changes before building them.

## Local development

```bash
python tools/setup_demo.py
python server.py
python -m unittest discover -s tests -q
```

No runtime dependencies are required. Unit and HTTP tests create temporary tables
and do not modify your ongoing campaign. Node.js enables the browser catalog tests.
Check JavaScript changes with `node --check web/app.js` or the relevant file.

For optional map and browser checks, use a virtual environment:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install shapely playwright
python -m playwright install chromium
python tests/browser_public_smoke.py
python -m unittest discover -s tests -p test_dungeon_maps.py -q
```

The map tests skip when Shapely is absent. PNG/browser checks require Chromium.
Windows launcher checks run with `python tests/launcher_smoke.py`.

## Before opening a pull request

- Preserve revision checks, stable request IDs and atomic writes.
- Keep public state separate from private DM material. A UI-hidden field is public.
- Add meaningful regression tests for behavior changes, using original synthetic fixtures.
- Keep player actions, spending and reactions explicit.
- Identify rule sources and distinguish house rules from SRD text.
- Include reproducible validation and update documentation when behavior changes.
- Do not contribute commercial PDFs, OCR, private saves, credentials or unlicensed assets.

Original code contributions use MIT; SRD-derived rules retain CC BY 4.0 attribution.
See [ATTRIBUZIONI.md](ATTRIBUZIONI.md).
