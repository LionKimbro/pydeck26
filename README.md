# PyDeck 26

PyDeck 26 is a persistent cockpit for entering, understanding, and working within Lion's `python-2026-03` project habitats.

PyDeck is launched from the root of one project and stays bound to that project for its whole process. Its first functional slice is a project masthead plus a living Whiteboard with recoverable historical snapshots.

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
docs/whiteboard/<local-timestamp>.txt
```

Snapshots are immutable. Recalled snapshots are read-only in this first slice; use **Restore as Current** to copy one safely into the live Whiteboard.

## Project memory

The seed brief is preserved in [docs/raw/001__pydeck26-application-brief.md](docs/raw/001__pydeck26-application-brief.md).
