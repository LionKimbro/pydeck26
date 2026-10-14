# PyDeck 26

PyDeck 26 is a persistent cockpit for entering, understanding, and working within Lion's `python-2026-03` project habitats.

PyDeck is launched from the root of one project and stays bound to that project for its whole process. Its cockpit includes curated resource jumpers, a project dictionary and JSON editor, conversation records, pinned ideas and an ideas directory, and a living Whiteboard with historical snapshots.

## Run

Initialize PyDeck's project-local Whiteboard storage once:

```text
pydeck26 init
```

Then open the cockpit from that same project root:

```text
pydeck26
```

The GUI can also initialize an uninitialized project. PyDeck creates only its own working files:

```text
db/pydeck26/whiteboard.txt
db/pydeck26/settings.json
db/pydeck26/conversations.json
db/pydeck26/resources.json
docs/whiteboard/<local-timestamp>.txt
```

The optional dictionary lives in `db/pydeck26/dictionary-entry.json`; ideas live in `db/ideas.json`. Their files are created when saved.

Snapshots are immutable. Editing recalled history makes a new current Whiteboard and retains the previous current text as a virtual snapshot. Only Current can be snapshotted to disk.

Ctrl+S saves working project edits. Resource changes, idea saves, and valid additional dictionary JSON request persistence immediately. Normal close flushes drafts and waits for completed writes. Invalid additional JSON stays visible and unsaved; repair it before closing the project, or close its editor to discard it.

Tk runs on the main thread. Core, Mem, and Disk run as supervised workers with explicit state ownership and Mobile Stack continuations. See [architecture and save behavior](docs/code/architecture.md).

## Tests

```text
python -m pytest -q
```

The suite includes fresh-process real-Tk checks against temporary project roots. A desktop with Tk support is required for those checks.

## Project memory

The seed brief is preserved in [docs/raw/001__pydeck26-application-brief.md](docs/raw/001__pydeck26-application-brief.md).
