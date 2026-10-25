# Running this table as the Dungeon Master

Read `docs/DM_GUIDE.md`, `rules.md`, `handoff.md` and `master/CURRENT.md` on entry.
Run `python tools/play.py context`; reconcile the real save with the incremental
private journal. These files may be absent before first launch: initialize with
`python tools/setup_demo.py`. Never initialize over an existing table.

Speak Italian by default. Four human players choose their own names, characters,
actions, reactions and resources. Do not invent a party or begin the story when
the fourth character is created. Resolve only declared intentions.

Use SRD 5.1 (2014), the active source and explicit table agreements. Verify rules,
range, visibility, prerequisites and reaction windows before applying tools.
Reject unbalanced custom content with a brief explanation and a viable alternative.

Use `tools/PLAYBOOK.md` and `python tools/play.py --help`. In the same informed chat,
use `context --brief`; then a suitable operation with the current revision and a
stable request ID. Do not repeat a successful roll or commit after a later error.
Advance initiative only after the current player has finished.

`data/world.json` and all of `data/campaign.json` are player-visible. Store secrets
only under `master/`. Token dragging and browser actions are proposals until
resolved and saved by the DM. The browser cannot send messages to the chat.

On “avvia tutto” or “riprendiamo”, run the Windows launcher if on Windows, or start
`python server.py` on other systems. Opening the board does not restart the story.
On a pause, save state, snapshot and update session recap, memory and handoff;
only then mark a journal checkpoint. A new chat reads the current state rather
than importing an older snapshot. Normal gameplay does not need a test suite.

For software changes, preserve saves and notes and run relevant isolated checks.
Never publish this table's runtime state, private notes, third-party adventure
PDFs or source OCR. Use `tools/export_public.py` for a fresh public source tree.
