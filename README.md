# PyDeck 26

PyDeck 26 is a persistent cockpit for entering, understanding, and working within Lion's `python-2026-03` project habitats.

The interface uses a shaded phosphor-green palette inspired by vintage computer monitors, with dark green surfaces and brighter green headings and controls.

PyDeck is launched from the root of one project and stays bound to that project for its whole process. Its cockpit includes curated resource jumpers, a project dictionary and JSON editor, conversation records, pinned ideas and an ideas directory, and a living Whiteboard with historical snapshots.

The cockpit has tabs and configurable rows. Each row can contain one, two, or three hosting slots. A slot's dropdown offers existing panels and **[+ Notes]** to create an independent writing panel. **×** unhosts a panel while preserving its data; **Ctrl-click ×** permanently deletes the panel record and removes it from every tab. Notes text is deleted with its panel. Built-in project files are retained; a deleted project instrument can be explicitly created again using its **[+ Type]** dropdown choice. Project panels can appear on multiple tabs, once per tab; Notes panels have their own identities and text.

Only empty slots show the chooser. Occupied slots place **×** at the right end of the panel's title row; unhosting reveals the chooser again.

Choose **[+ Image]** for an image panel. Browse for a JPEG, PNG, or GIF, paste an image or one image file from the clipboard, or drop a file onto the empty canvas. Previews fit the available space without upscaling. **Red pen** adds drawing marks; **Clear image** returns to the import controls. Drawings survive resizing and restart. GIFs show their first frame.

Use **+ Tab**, **Rename tab**, and **Remove tab** in the toolbar, and **+ Add row** at the bottom of the tab. A row's rail offers **x1/x2/x3**, **↑/↓** to reorder it, and **×** to remove it. Drag column dividers to change widths and the shaded edge beneath a row to change its height. Tabs scroll vertically and remember their position. Removing tabs or rows preserves their panels so they can be hosted again.

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

Layout, hosting, selected tab, sizes, scroll positions, and independent Notes live in `db/pydeck26/workspace.json`. Existing projects start with a Cockpit tab matching the original five-panel layout; no conversion of the existing project records is needed. Layout changes request persistence immediately; Notes text saves with Ctrl+S, a layout transition, or normal close.

Imported image originals are copied to `db/pydeck26/assets/`. Image references and red-pen strokes live in the workspace file. Image imports and clearing save immediately; drawing edits save after 60 seconds idle, Ctrl+S, layout changes, or normal close. Clearing or deleting an image panel retains its asset file, as in Today.

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
