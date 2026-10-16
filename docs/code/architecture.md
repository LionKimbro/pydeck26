# PyDeck 26 machine architecture

This is the current implementation map, updated 2026-10-15. The reference is
Today's `docs/architecture-review.md` and current `src/today` implementation.

## Ownership

| Module | Owns | Execution |
| --- | --- | --- |
| `tk.py`, `framing.py`, and editor modules | Widgets, bindings, tab/row/slot framing, native dialogs, editor drafts, independent presentation records | Main thread |
| `theme.py` | Shared phosphor-green palette and Tk/ttk appearance defaults, installed before window construction | Main thread |
| `panel_geometry.py` | Live internal panel splits, drag tracking, and deferred proportion restoration | Main thread |
| `core.py` | Working project documents, dirty generations, selected conversation, Whiteboard history cursor, semantic reducer events and effects | Core worker |
| `mem.py` | Canonical project documents and revision; acceptance and persistence scheduling | Mem worker |
| `disk.py` | Project loading, document writes, historical snapshot reads/creation, filesystem path validation | Disk worker |
| `image.py` | Clipboard acquisition, image validation, EXIF correction, fitted RGBA preview preparation | Image worker |
| `image_core.py` | Import/preview request tokens, presentation errors, working drawing edits | Core worker |
| `image_ui.py` | Native image input controls/drop reception, Tk image objects, normalized drawing drafts | Main thread |
| `git_ui.py` | Checkboxes, commit draft, menus, read-only file/diff viewers, independent repository presentation | Main thread |
| `git_core.py` | Git request identities, serialization, repository snapshots, result acceptance | Core worker |
| `git_worker.py` | Git subprocesses, status parsing, repository file reads/deletion, fetch/push | Temporary Git instance |
| `captains_log.py` | LSF conversion, validation, revision chains, independent log record operations | Pure operations; LSF I/O via Disk |
| `captains_log_core.py` | Save validation, working proposals, durable entry projection and generation-indexed acknowledgments | Core worker |
| `captains_log_ui.py` | Entry drafts, selections, minute clock, modifier state, log widgets | Main thread |
| `machine.py` | Permanent/dynamic runtime registry, thread-local runtime selection, supervised workers, routing, lifecycle and fatal latch | Shared mechanics |
| `mobile_stacks.py` | Traveling continuation frames and registers | Accessed through each worker's runtime |
| `main.py` | Project-root binding, queues, startup, main loop and final joins | Main thread |
| `storage.py` | Existing synchronous text/JSON primitives; used by Disk during GUI execution and by the standalone CLI init command | Disk or CLI |

`cockpit.py` preserves the CLI's launch entrypoint. `framing.py` supplies the
Today-style outer workspace around the existing project instruments in `tk.py`.
There is no dependency on Today; PyDeck retains project-local records rather
than adopting Today's day bundles. Its image panel behavior follows Today.

## Workspace and hosting

`workspace.py` describes plain tab, row, position, and panel records. The
`workspace` document is canonical in Mem, a working copy in Core, and an
independent presentation copy in Tk. Mem validates it when loading and accepting
commits. Core applies semantic transitions to an independent proposal and
reports expected invalid operations as status data, without publishing a
partially changed layout.

Tabs own ordered row identities. Rows carry a column count (one, two, or three),
pixel height, and cumulative column-divider proportions. A position identity is
derived from its row and column: `<row-id>/column-<n>`. Positions host panel IDs
or null. Changing hosting changes presentation, not the panel record.

Structure, Dictionary, Conversations, Ideas, and Whiteboard have stable
project-panel identities and continue to use their existing data files. Notes
panels have independent IDs and text within the workspace document. The same
panel may be hosted on different tabs, but at most once in any given tab.
Shrinking a row unhosts discarded slots; removing a row or tab removes only
its layout records. All panel records survive and remain available to host.
The final tab cannot be removed; a tab may have no rows and offers Add Row.

A slot's dropdown combines existing panel choices with creation choices such
as `[+ Notes]`. `framing.PANEL_CREATION_CHOICES` declares the creation commands
in one place. No separate Notes button is needed. Missing project instruments
offer explicit `[+ Type]` choices, so deleting one does not cause automatic
resurrection at startup.
Only empty slots construct a chooser. Hosted panel builders return their title
row, where framing inserts the × control at the far right, alongside existing
Copy/Snapshot/Rename actions. There is no separate slot header above a hosted
panel. Unhosting rebuilds the slot as an empty chooser.

Ordinary × submits `UNHOST_PANEL`. Ctrl-click × submits `DELETE_PANEL` and
suppresses the ordinary button press/release behavior. Deletion removes the
panel record and all hosting references across every tab. Notes payloads are
owned by that record and are deleted with it. Project instruments refer to
external project-owned records: deleting their workspace panel does not erase
the dictionary, conversations, ideas, resources, Whiteboard, or historical
files. Explicit recreation attaches a fresh instrument record to those files.
Obsolete Notes edits targeting a deleted identity are ignored. Serialized,
generation-tracked workspace writes keep older saves from restoring deleted
records.

Existing projects without a workspace file receive a deterministic Cockpit tab
with the original five instruments arranged in two/two/one-column rows.
Startup does not write this default or rewrite existing records. Layout edits
and explicit project save persist `db/pydeck26/workspace.json`. Unknown
extension fields survive edits to established record fields.

Tk uses a notebook and vertically scrollable canvas for each tab, rendering
panel contents only for the active tab. Structural signatures trigger widget
reconciliation only when tab/row/hosting structure changes. Text edits and save
acknowledgements leave widgets and insertion positions intact. Geometry changes
update row height and divider positions without rebuilding the panels. Width
changes restore relative divider proportions; each tab retains its scroll
position. Pending drafts are submitted before switching tabs or changing
hosting. Pending Text modification events are also flushed before asynchronous
projections can overwrite them.

Column restoration is coalesced at Tk idle after the row maps, resizes, or its
hosting frames change geometry. Its cache includes achieved divider positions,
not just outer width: nested panels can trigger a later paned-window layout at
the same width. Restoration pauses during a sash drag; release captures the new
presentation proportions before submitting them to Core. Pending callbacks are
cancelled when rows are rebuilt. Two passes restore x3 dividers even when a
divider must move beyond its neighbor's previous position. The existing workspace
format stores these proportions and row heights across tab switches and restart.

Captain's Log and Conversations additionally store `split-proportion` on their
project panel record, independent of the hosting row. The field is optional for
existing workspaces and defaults to 0.4 of the available width for the list.
`panel_geometry.py` registers each active two-pane split, suspends restoration
during dragging, and restores after map/resize/hosting-frame geometry changes.
Only a user drag emits `SET_PANEL_SPLIT`; Core validates the finite proportion
and supported panel type, then persists workspace through Mem/Disk. A panel
shared across tabs shares its internal proportion. Widget rebuilds cancel pending
restoration callbacks. Divider changes neither rebuild editor fields nor submit
Captain's Log drafts. Conversations uses a paned window in place of its previous
fixed grid so its internal split can also be adjusted.

There are five permanent queues: Core, Mem, Disk, Image, and Core-to-Tk commands.
Image is one supervised permanent worker in PyDeck, rather than Today's dynamic
per-operation instances. Its traveling stacks still continue through Disk and
return to the same Image machine; CPU work never enters the Tk thread.
Tk sends plain semantic events. Core translates returned Mobile Stacks into
copied reducer events, reduces its local event list, and dispatches effects.
The reducer mutates module-owned state; it is not a pure state-in/state-out
function. Effects create stacks or emit declarative Tk commands.

Unlike Today, Tk drains commands with a 20 ms main-thread callback rather than
a worker-generated Tk virtual event. Workers never call Tk APIs or receive Tk
objects. The same callback observes fatal worker failure independently of Core.

## Image panels

`[+ Image]` creates an independent workspace panel with an asset reference and
normalized red-pen strokes. Import uses:

```text
Tk -> Core -> Image -> Disk (source read, when needed) -> Image (validate)
   -> Disk (asset write) -> Image -> Core (token check) -> Mem -> Disk
```

Tk owns native browse/drop controls and Tcl list decoding of paths containing
spaces. Clipboard acquisition and PNG serialization of clipboard pixels happen
in Image. All file reads/writes happen in Disk. JPEG/PNG/GIF format validation
uses actual content, not the original filename extension. Imports copy source
bytes without changing the original file.

Assets use generated `assets/image-<uuid>.jpg|png|gif` references relative to
`db/pydeck26`. Disk validates their shape and resolved containment, publishes
them via temporary-file replacement, and returns expected I/O errors as data.
Clearing removes the reference and drawing; panel deletion removes the record.
Both retain asset files, and obsolete import completion may leave an orphan.
There is no automatic asset garbage collector.

Preview requests travel Image -> Disk -> Image -> Core -> Tk. Image decodes the
first frame, applies EXIF orientation, fits without upscaling, and returns RGBA
bytes. Only Tk constructs and retains `PhotoImage`. Geometry requests debounce
for 100 ms. Core rejects obsolete request tokens/assets; Tk also rejects results
for a destroyed host or outdated canvas bounds. Pixels never enter Mem records
or workspace JSON. Expected bad inputs/missing assets produce panel errors,
while broken worker invariants still trigger fatal application shutdown.

Red pen is a separate Canvas layer. Stroke points are normalized to the fitted
image and pen width to its shorter dimension; resizing reprojects this data.
Completed strokes reach Core immediately and remain working until the 60-second
idle save, project save, layout transition, or normal close. Before close or a
layout rebuild, Tk finishes any active stroke. Originals remain byte-for-byte
unchanged. Export flattening and GIF animation are not implemented, matching
Today's current boundaries.

Normal shutdown waits for outstanding Image continuations. Results arriving
after the semantic close request are discarded; unfinished imports are not
promised as successful commits. Main joins Image after Core and before Disk.
Fatal failure wakes Image through the same runtime exception boundary as the
other permanent workers.

## Loading and continuation ownership

Startup and GUI initialization use:

```text
Core -> Disk / LOAD_PROJECT -> Mem / INSTALL_PROJECT -> Core / PROJECT_RETURNED
```

The project root is installed before workers start and does not change.
Starting an uninitialized project does not create files. GUI initialization
uses the existing idempotent storage operation and retains working drafts.

Mobile Stack frames are bottom first. The last frame names the next machine
and handler. Runtime pops the handler's frame after the handler returns; a
handler may declare continuation frames for runtime to append afterward.
Publication clears the sender's active stack slot before queueing the stack.
A receiver refuses to replace an active stack and validates its destination.
Retained results are copied before the traveling stack finishes or continues.

Mem, Core, Tk, and in-flight proposals have independent nested containers.
Threads do not communicate through implicit current-record registers.

## Editing and persistence

Core retains working records. Tk identifies conversation and idea drafts by
record identity; dialog commits do not silently retarget the current selection.
Idea editors hold independent drafts, so cancellation cannot mutate Core or Mem.
Unrecognized document and record fields survive ordinary subset edits.

Compact dictionary, conversation, and Whiteboard edits wait for Ctrl+S or
normal close. Structure edits, explicit idea saves, and valid additional JSON
request immediate persistence. This preserves the existing save timing.
Layout transitions also request persistence immediately. Independent Notes
edits remain working until project save, a layout transition, or normal close.

Core sends one revisioned commit at a time and coalesces further requests while
that commit travels. Each proposal captures document generations and independent
document copies. Mem verifies the base revision, accepts canonical records,
increments its revision, and schedules Disk through a continuation:

```text
Core -> Mem / COMMIT_PROJECT -> Disk / WRITE_DOCUMENTS -> Core / COMMIT_RETURNED
```

Mem acceptance and Disk completion are distinct milestones. This implementation
returns to Core only after Disk has completed the requested writes. Core clears
dirty state only for generations that still match the submitted proposal. Newer
edits remain dirty; normal close submits them before exit. A canonical revision
conflict is a broken invariant because Core is the sole serialized proposer.

Disk retains existing locations and formats:

- `db/pydeck26/whiteboard.txt`
- `db/pydeck26/dictionary-entry.json`
- `db/pydeck26/conversations.json`
- `db/pydeck26/resources.json`
- `db/ideas.json`
- `db/pydeck26/workspace.json`
- `db/pydeck26/assets/image-<uuid>.jpg|png|gif`
- `docs/whiteboard/<local-timestamp>.txt`

Mutable files use atomic temporary-file replacement. History files use exclusive
creation; a timestamp collision becomes an ordinary status message. A save of
several documents is not a multi-file transaction or a power-loss durability
guarantee. Existing settings are preserved but remain unused.

History reads have request tokens. A newer selection or text edit invalidates
older reads. Editing recalled history promotes that text into Current and
retains the former Current in one virtual snapshot, without changing disk
history. Only Current may be snapshotted.

Tk events carry monotonic sequence numbers. Projections predating submitted
draft edits are ignored; projections suppress edit notifications and avoid
replacing unchanged entry/text contents. Additional JSON uses valid-only
debounced submission; pending edits are checked before save/close. Invalid
JSON never overwrites the last valid document.

Conversation Entry fields use StringVar write traces to capture edits during
the widget change, including paste/IME updates, rather than waiting for
KeyRelease. `tk.conversation_draft` owns the current record ID and last submitted
field values. Edits are compared with that draft, so returning to an earlier
value before Core acknowledges it still submits the change. Same-record Core
views and save acknowledgements update the list/status, not the live editor
fields. Another record selection or newly built widgets explicitly loads the
editor. Conversation rows reconcile by identity without clearing/reselecting
the whole tree during typing, preserving list scroll and selection.

This follows Today's ordinary `TEXT_CHANGED`/save-acceptance behavior: working
state changes do not automatically emit text replacement commands. The prior
KeyRelease binding left a gap after KeyPress inserted text but before it had a
sequence number; an older accepted view could replace the new text in that gap.

## Git panel and temporary machines

Git is an optional `project-git` instrument created through `[+ Git]`, retaining
the original default cockpit layout. It inspects the enclosing repository from
the fixed project root. Repository state is transient; Mem stores only hosting
records. Tk owns the commit-message draft and selected paths. Git state/viewer
commands bypass project-document sequence filtering and never replace that draft.
Only successful commits clear it, and only when it still matches the submitted
message. Refreshing reconciles file rows without resetting existing selections.

Core serializes all Git requests. A frame destination `{"new": "GIT"}` asks the
router to create a unique `GIT-<uuid>` address, inbox, and supervised thread. The
frame is replaced with that address before ownership transfers through its queue.
Registered kinds share the permanent workers' fatal boundary. An instance may
continue through other machines and wait for a return at its own address; it is
not implicitly retired after a handler. The Git handler returns a fresh status
snapshot or expected error as data and explicitly requests retirement after its
final handoff. Tk's command poll joins exited dynamic workers and removes their
registry entries. Registry changes and creation/shutdown publication use an RLock.

Each Git instance keeps its working root in its own runtime, never a shared
module register. Subprocesses use argv and literal pathspecs, no shell or pager,
and disable external diff/textconv. Ordinary commit hooks still run. Commands
cannot ask for terminal input, and have a 120-second timeout that terminates the
process tree. A timeout reports that the operation may already have completed.
No Git command or repository-file access is performed by Disk or Tk.

Porcelain NUL-delimited status preserves filenames and rename sources. A file
may be listed on both sides of the index. Actions check the displayed revision,
then recheck selected records' index/file stamps in the worker. Commit rechecks
the complete index/HEAD stamp. These checks catch stale UI requests; Git's own
index locks still govern competing external Git processes. Destructive actions
reject directories, submodules, `.git` paths, and escaped parents; symlink deletion
unlinks the link. A staged rename's restore includes both names. Delete preserves
the index; Discard restores both index and worktree, including unstaged edits.

Status metrics also stay in the Git worker: batched `cat-file` blob sizes describe
staged versions, while lstat sizes describe working files. NUL-delimited numstat
provides side-specific added/removed line counts, including rename pairs and
binary markers. Untracked text is streamed to count additions without retaining
its contents; symbolic links are inspected without following their targets.
Tk only formats these plain byte counts and diff records for the two extra columns.

Passive five-second polling reads local status. Explicit Refresh fetches the
configured upstream remote, then reads status even if fetch fails. Ahead/behind
counts use local upstream tracking refs. Push is an ordinary non-forced `git push`,
available only when ahead with no behind count; branches without an upstream
need configuration outside the panel. Behind/diverged branches require an
external pull/reconciliation. File viewers cap text at 2 MiB and identify binaries.

## Captain's Log

The optional `project-captains-log` instrument hosts the `captains-log` document.
Disk loads `db/pydeck26/captainslog.lsf` through `lsf.loadstr`; absence produces an
in-memory header only and never creates a file at startup. Mem owns an independent
canonical LSF section list and validates it at load and commit boundaries. Core
owns a working copy. Disk writes `lsf.savestr` output using atomic replacement.

Every entry has a GUID, date/time to seconds, optional hook, space-separated tags,
major flag, and `indent: 2`. Body lines, including blanks, receive exactly two
storage-prefix spaces so section-like lines remain body text. Existing indentation
is retained after that prefix. Unrecognized metadata and the file header survive
saves. Normal revisions append a fresh GUID with `supersedes` and `modified-on`,
preserving original date/time and previous sections. Current entries are GUIDs
not referenced by another revision. Validation rejects duplicate GUIDs, stale or
branching supersession, and mismatched revision timestamps. Ctrl+Save Over replaces
the current section at its existing index, keeps its GUID and supersedes link,
and removes modified-on metadata. New creations are ignored if their original
date/time second is already present; revisions are exempt from that guard.

Tk owns drafts keyed by entry GUID plus one permanent `new` draft. Entry variables
and Text modifications capture edits locally; no draft is sent to Core until the
log Save button is used. Drafts survive entry/tab/hosting changes until process
exit. A minute-boundary callback updates the new-entry row inside Tk, including
date rollover, with no reducer message. Major entries are bold; dirty rows are
red even when selected. Saved revisions show Last edited before the hook field.

Save submits a copied draft, expected entry, overwrite intent, and request ID.
Core checks the current GUID/version, validates fields, takes its own local Save
timestamp, mutates an independent proposal, and requests the ordinary Mem/Disk
commit. Its log presentation remains at the last persisted generation. Only a
COMMIT_RETURNED from Disk advances that presentation and acknowledges matching
save requests. Log acknowledgments bypass general project sequence filtering.
Tk clears/rekeys only the submitted draft, preserving newer typing and insertion
position during a held write; a rejected draft stays editable. No project save,
framing flush, or shutdown event implicitly posts log drafts. Normal close waits
for explicitly submitted saves, then discards remaining Tk drafts without a dialog.
Shared multi-panel close dialogs remain a separate idea in `db/ideas.json`.

## Shutdown and failure

Normal close flushes pending widget drafts and additional JSON, then sends a
semantic shutdown request. Core rejects subsequent user edits, waits for all
outstanding continuations, and persists its latest dirty generations. Only
then does it retire, stop Mem, and tell Tk it may destroy the root.

Core waits for the active Git operation, including result acceptance, before
closing dynamic creation. Main joins Core and remaining dynamic workers, reaps
their addresses, then joins Image and Mem, queues Disk's sentinel after its producers stop,
then joins Disk. Only the main thread joins/reaps workers. The same orchestration
is used by GUI execution and worker tests.

Unexpected worker exceptions or unexplained returns latch fatal failure, print
a traceback, and wake all workers. Tk closes even when Core itself has died.
Main joins workers and exits with status 1. Fatal exit does not attempt an
emergency save. Like Today, shutdown is cooperative: no watchdog or forced
termination handles an arbitrary worker stuck inside a handler. Git subprocesses
have their own bounded timeout as described above.

## Verification

`test_captains_log.py` checks LSF body fidelity, literal section delimiters,
metadata preservation, tag validation, same-second creation guards, revision
shadowing, in-place overwrite, durable acknowledgments, independent machine
ownership, and close during a held write. `gui_captains_log.py` exercises actual
Tk hosting, draft styling, newer typing during a held save, revisions and Ctrl-click
Save Over, minute/date rollover without Core events, tab changes, and discard on
exit followed by restart. It never creates notes in the real project.

`test_dynamic_machines.py` exercises unique creation addresses, continuations
through another machine, explicit retirement, Main-only reaping, shutdown gates,
and fatal dynamic failures. `test_git_panel.py` uses disposable repositories and a
local bare remote for partial staging, both diff sides, rename/add/delete/discard,
literal filenames, stale index/files, failed commits, first-commit behavior,
ahead/behind/divergence, push, and close during an operation. `gui_git_panel.py`
exercises actual Tk hosting, filename checkboxes, menus/viewers, commit draft
preservation/clearing, and push-button states in a fresh interpreter.

`tests/test_machines.py` exercises actual workers and queues: snapshot isolation,
ownership transfer, delayed disk writes, newer edits during a save, close-time
flushes, stale history, immutable snapshots, optional initialization, ordered
resource records, preserved extensions, path containment, and fatal failures.

`tests/test_gui_lifecycle.py` runs `gui_lifecycle.py` in fresh processes against
temporary roots. It exercises real Tk startup, editor events, invalid/valid JSON,
close before a pending debounce, persisted results, and injected Core/Mem/Disk
failure with no surviving workers. A failed final Disk write produces status 1
instead of a successful saved exit. It does not replace manual desktop checks
of native dialogs, Explorer launches, or clipboard interoperability.

`tests/test_workspace.py` checks panel identity, sharing across tabs, shrinking
rows without deleting data, row order, and rejected illegal layouts.
`tests/test_gui_workspace.py` runs a fresh-process real-Tk roundtrip using the
actual notebook, slot dropdowns, x3 button, Notes controls, resize handles,
dividers, and scroll commands. It switches tabs with pending text edits,
closes with a newer Notes draft, restarts, and verifies restored text, selected
tab, row sizes, divider ratios, and scroll position. Worker tests additionally
verify canonical ownership and byte-for-byte preservation of existing project
record files during layout changes.

`gui_panel_delete.py` exercises real dropdown creation and Ctrl-modified button
events, including suppression of ordinary unhosting, deletion from multiple
tabs, persistence across restart, and explicit project-instrument recreation.
Worker tests hold an earlier save during deletion and verify that its eventual
return and an obsolete draft cannot resurrect the deleted panel.

`test_image_panels.py` checks supported formats, clipboard acquisition, EXIF,
fitted RGBA pixels, invalid input, reference containment, stale imports/previews,
worker failure, and immutable source/assets. `test_gui_image.py` runs a real-Tk
roundtrip: dropdown creation, browse callback, fit, red-pen strokes, resize,
close during an active stroke, restart, clear, and a dropped path with spaces.
Clipboard interoperability and physical OS drag gestures remain manual checks.

`test_gui_conversation_typing.py` holds Core while Entry changes are made and
older views arrive before KeyRelease. It checks all conversation fields,
cursor/selection/list-scroll preservation, same-record refreshes, reverting
unacknowledged edits, variable-driven input, navigation, and persisted results.
The standalone reproduction's optional `--baseline` mode loads the old handlers
from revision `8e8227b`; it reproduces the original replacement before the fix.
