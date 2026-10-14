# PyDeck 26 machine architecture

This is the current implementation map, updated 2026-10-13. The reference is
Today's `docs/architecture-review.md` and current `src/today` implementation.

## Ownership

| Module | Owns | Execution |
| --- | --- | --- |
| `tk.py` and editor modules | Widgets, bindings, native dialogs, editor drafts, independent presentation records | Main thread |
| `core.py` | Working project documents, dirty generations, selected conversation, Whiteboard history cursor, semantic reducer events and effects | Core worker |
| `mem.py` | Canonical project documents and revision; acceptance and persistence scheduling | Mem worker |
| `disk.py` | Project loading, document writes, historical snapshot reads/creation, filesystem path validation | Disk worker |
| `machine.py` | Permanent runtime registry, thread-local runtime selection, supervised workers, routing, lifecycle and fatal latch | Shared mechanics |
| `mobile_stacks.py` | Traveling continuation frames and registers | Accessed through each worker's runtime |
| `main.py` | Project-root binding, queues, startup, main loop and final joins | Main thread |
| `storage.py` | Existing synchronous text/JSON primitives; used by Disk during GUI execution and by the standalone CLI init command | Disk or CLI |

`cockpit.py` preserves the CLI's launch entrypoint. The existing visual cockpit
is retained in `tk.py`; panel types, tabs, and arbitrary placement are future
work. There is no new dependency on Today.

There are four permanent queues: three worker inboxes and Core-to-Tk commands.
Tk sends plain semantic events. Core translates returned Mobile Stacks into
copied reducer events, reduces its local event list, and dispatches effects.
The reducer mutates module-owned state; it is not a pure state-in/state-out
function. Effects create stacks or emit declarative Tk commands.

Unlike Today, Tk drains commands with a 20 ms main-thread callback rather than
a worker-generated Tk virtual event. Workers never call Tk APIs or receive Tk
objects. The same callback observes fatal worker failure independently of Core.

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

## Shutdown and failure

Normal close flushes pending widget drafts and additional JSON, then sends a
semantic shutdown request. Core rejects subsequent user edits, waits for all
outstanding continuations, and persists its latest dirty generations. Only
then does it retire, stop Mem, and tell Tk it may destroy the root.

Main joins Core, joins Mem, queues Disk's sentinel after its producers stop,
then joins Disk. Only the main thread joins/reaps workers. The same orchestration
is used by GUI execution and worker tests.

Unexpected worker exceptions or unexplained returns latch fatal failure, print
a traceback, and wake all workers. Tk closes even when Core itself has died.
Main joins workers and exits with status 1. Fatal exit does not attempt an
emergency save. Like Today, shutdown is cooperative: no watchdog or forced
termination handles a worker stuck inside a handler.

## Verification

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
