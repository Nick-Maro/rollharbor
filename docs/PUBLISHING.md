# Publish the software, keep your table

A working game can contain player saves, hidden story details, supplied PDFs and
older Git commits that still contain those files. Adding `.gitignore` does not
remove tracked files or their history.

Create a **new source directory** using the explicit public allowlist:

```bash
python tools/export_public.py ../rollharbor-public
```

The destination must not exist. The exporter refuses to merge with or overwrite
another directory, copies no `.git` history, replaces table-specific instructions
with public templates, and excludes runtime folders and adventure packs. The
hash manifest `PUBLIC_EXPORT.json` describes the copied source files.

In that new directory, validate before preparing a commit:

```bash
python tools/setup_demo.py
python tools/dnd.py validate
python -m unittest discover -s tests -q
git init -b main
git add .
python tools/check_public.py
git status --short
git diff --cached --stat
```

Inspect the staged paths: `data/`, `master/`, `saves/`, `campaigns/`, `sessions/`,
`handoff.md`, `rules.md`, PDFs and credentials must not be staged. Then create a
local commit. Connecting a remote and pushing are separate publication steps;
review the [release checklist](RELEASE_CHECKLIST.md) first.

`tools/check_public.py` rejects private runtime paths and common credential-file
names in the Git index, including files force-added despite ignore rules. It
supplements a dedicated secret scanner. Before a release, scan both the current
source and the entire history being pushed with a tool such as Gitleaks, using
redacted reports stored outside the repository. Review example fixtures separately
from real credentials; never publish scanner reports containing secret values.

Only publish this clean checkout. The original private working repository retains
the existing campaign and its history. Do not solve this by force-pushing a
rewritten private repository.

For future software changes, export into another new directory and review the
diff against your public checkout. This intentionally avoids copying arbitrary
new files from a live campaign into the release.
