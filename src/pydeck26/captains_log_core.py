"""Core owns accepted log changes and acknowledges Save only after Disk returns."""

from copy import deepcopy
from datetime import datetime

from . import captains_log

entries = []  # Last durably accepted projection; never aliases a Tk record.
pending = {}  # Request ID -> required log generation and saved entry.


def initialize_log_state():
    entries.clear()
    pending.clear()


def install_document(document):
    entries[:] = captains_log.get_current_entries(document)


def current_time():
    return datetime.now().astimezone().replace(microsecond=0)


def reply(request_id, result):
    from . import core
    core.effects.append({"type": "TK", "command": {"type": "CAPTAINS_LOG_RESULT",
        "request-id": request_id, "entries": deepcopy(entries), **deepcopy(result)}})


def save_draft(event):
    from . import core
    request_id = event["request-id"]
    if request_id in pending:
        return
    if not core.g["initialized"]:
        reply(request_id, {"ok": False, "error": "Initialize PyDeck before saving log entries."})
        return
    proposal = deepcopy(core.documents["captains-log"])
    try:
        result = captains_log.save_entry(proposal, {**event, "moment": current_time()})
    except (ValueError, KeyError, TypeError) as error:
        reply(request_id, {"ok": False, "error": str(error)})
        return
    if not result["changed"]:
        reply(request_id, {"ok": True, "entry": result["entry"]})
        return
    core.documents["captains-log"] = proposal
    core.touch_document("captains-log")
    pending[request_id] = {"generation": core.generations["captains-log"], "entry": result["entry"]}
    core.request_commit({"captains-log"})


def accept_persisted_commit(event):
    generation = event["generations"].get("captains-log")
    if generation is None:
        return
    install_document(event["documents"]["captains-log"])
    for request_id, record in list(pending.items()):
        if record["generation"] <= generation:
            reply(request_id, {"ok": True, "entry": record["entry"]})
            del pending[request_id]
