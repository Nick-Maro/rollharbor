# Getting started

## Requirements

Python 3.10 or newer and a current browser. The core server has no pip dependencies.
Windows has launch/stop scripts; macOS and Linux use the same Python entry point.
The game interface is Italian. Four people share one local board.

From the project directory:

```bash
python server.py
```

Visit `http://127.0.0.1:8765`. On systems where Python is named `python3`, use
`python3` in the commands. On Windows, `py -3 server.py` is another option.
The first launch initializes `examples/demo/` into local runtime folders.
The initialization command is also available explicitly:

```bash
python tools/setup_demo.py
python tools/dnd.py validate
```

On Windows, `AVVIA.cmd` opens a browser and finds a port from 8765 through 8775.
Use the address printed by the launcher. `ARRESTA.cmd` stops the verified server
for that folder. For a technical check without opening a browser:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\AVVIA.ps1 -Json -NoBrowser
```

## First scene

Let each player create their own character in **Il gruppo**. A full group is ready
to play, but the story starts only when the players and DM agree. The demo opens
at Portolume with no accepted quest, no combat and no actions already chosen.

A human DM can use the CLI directly. A chat assistant must have access to this
folder and be told to follow `AGENTS.md`. The application does not create that
connection or send chat messages. See [the DM guide](DM_GUIDE.md).

## Your files

| Path | Role |
| --- | --- |
| `examples/demo/` | Versioned original starter, never your ongoing progress. |
| `data/world.json` | Player-visible world. |
| `data/campaign.json` | Current party, scene, resources, initiative and revision. |
| `master/` | Private DM notes, combat details and incremental log. |
| `sessions/`, `handoff.md`, `rules.md` | Your session summaries and table agreements. |
| `saves/` | Automatic backups and snapshots. |

The public distribution ignores runtime folders in Git. To move your ongoing
game, copy the whole folder, including ignored runtime files and any lawful local
sources. Browser notebook notes require their own export/import.

## Recovery

- **Port busy:** try `python server.py --port 8766`, then use that port in the browser.
- **Python missing:** install Python and reopen your terminal; Windows can use `py -3`.
- **Only one data file exists:** initialization refuses to overwrite it. Recover the
  missing file from your own backup. Do not replace a live table with the demo.
- **A save fails validation:** keep a copy, inspect the error, and restore a matching
  campaign backup through the board or DM tools. Startup never silently resets it.
- **A browser waits for the master:** send the prepared text to the chat; the board
  does not generate responses on its own.
- **Optional map tool reports a missing package:** install the documented extras in
  a virtual environment. Playing does not require those map-generation tools.

The server runs on the loopback interface. Remote access, accounts and Internet
hosting are outside this version's scope.
