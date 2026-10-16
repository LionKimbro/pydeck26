"""Captain's Log records and LSF conversion; no widgets or filesystem access."""

from copy import deepcopy
from datetime import datetime
import re
from uuid import UUID, uuid4

import lsf

TAG_PATTERN = re.compile(r"[a-z0-9-]+")


def make_document():
    return {"sections": [{lsf.TITLE: None, lsf.KEYS: {"title": "Captain's Log", "version": "1"}, lsf.BODY: ""}]}


def encode_body(body):
    return "\n".join("  " + line for line in body.split("\n"))


def decode_body(body):
    lines = body.split("\n")
    # Unindented trailing blank lines separate sections; indented blanks are note text.
    while lines and lines[-1] == "":
        lines.pop()
    if any(not line.startswith("  ") for line in lines):
        raise ValueError("Captain's Log body lines must have two leading spaces (indent: 2).")
    return "\n".join(line[2:] for line in lines)


def read_entry(section):
    keys = section[lsf.KEYS]
    return {"guid": keys["guid"], "date": keys["date"], "time": keys["time"],
            "hook": keys.get("hook", ""), "tags": keys.get("tags", ""),
            "major": keys.get("major", "false") == "true", "body": decode_body(section[lsf.BODY]),
            "supersedes": keys.get("supersedes"), "modified-on": keys.get("modified-on")}


def get_fields(entry):
    return {key: entry[key] for key in ("hook", "tags", "major", "body")}


def get_current_entries(document):
    entries = [read_entry(section) for section in document["sections"][1:]]
    shadowed = {entry["supersedes"] for entry in entries if entry["supersedes"]}
    return sorted((entry for entry in entries if entry["guid"] not in shadowed),
                  key=lambda entry: (entry["date"], entry["time"]), reverse=True)


def validate_fields(fields):
    if any(not isinstance(fields.get(key), str) for key in ("hook", "tags", "body")) or not isinstance(fields.get("major"), bool):
        raise ValueError("A log draft needs hook, tags, body text, and a major flag.")
    if "\n" in fields["hook"] or "\r" in fields["hook"]:
        raise ValueError("The hook must fit on one line.")
    if any(TAG_PATTERN.fullmatch(tag) is None for tag in fields["tags"].split()):
        raise ValueError("Tags must contain only lowercase a–z, digits, and dashes, separated by spaces.")


def validate_document(document):
    sections = document["sections"]
    if not sections or sections[0][lsf.TITLE] is not None:
        raise ValueError("Captain's Log needs an LSF file header.")
    known, shadowed = {}, set()
    for section in sections:
        if not isinstance(section[lsf.BODY], str) or not isinstance(section[lsf.KEYS], dict):
            raise ValueError("Invalid Captain's Log section.")
        for key, value in section[lsf.KEYS].items():
            if (not isinstance(key, str) or not key or any(char in key for char in ":\r\n")
                    or not isinstance(value, str) or any(char in value for char in "\r\n")):
                raise ValueError("LSF metadata must use single-line string keys and values.")
        if section is sections[0]:
            continue
        entry = read_entry(section)
        UUID(entry["guid"])
        if entry["guid"] in known:
            raise ValueError("Duplicate Captain's Log GUID.")
        title = f"{entry['date']} {entry['time']}"
        if datetime.strptime(title, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S") != title or section[lsf.TITLE] != title:
            raise ValueError("Log titles must match date and time to the second.")
        keys = section[lsf.KEYS]
        if keys.get("indent") != "2" or keys.get("major", "false") not in {"true", "false"}:
            raise ValueError("Log entries need indent: 2 and a true/false major flag.")
        validate_fields(get_fields(entry))
        if entry["modified-on"]:
            datetime.fromisoformat(entry["modified-on"])
        previous = entry["supersedes"]
        if previous:
            if previous not in known or previous in shadowed or title != known[previous]:
                raise ValueError("A log revision must supersede one earlier current entry with the same date/time.")
            shadowed.add(previous)
        known[entry["guid"]] = title


def load_text(text):
    document = {"sections": lsf.loadstr(text)}
    validate_document(document)
    return document


def save_text(document):
    validate_document(document)
    return lsf.savestr(document["sections"])


def save_entry(document, request):
    """Apply a validated creation/revision/overwrite to an independent proposal."""
    fields = deepcopy(request["fields"])
    validate_fields(fields)
    fields["tags"] = " ".join(dict.fromkeys(fields["tags"].split()))
    moment = request["moment"]
    target = request.get("guid")
    current = {entry["guid"]: entry for entry in get_current_entries(document)}
    if target:
        if target not in current or current[target] != request.get("expected"):
            raise ValueError("That entry has changed. Keep your draft and review the current version.")
        old = current[target]
        if fields == get_fields(old) and not (request.get("overwrite") and old["modified-on"]):
            return {"entry": old, "changed": False}
        source = next(section for section in document["sections"][1:] if section[lsf.KEYS]["guid"] == target)
        section = deepcopy(source)
        keys = section[lsf.KEYS]
        if request.get("overwrite"):
            keys.pop("modified-on", None)
        else:
            keys.update({"guid": str(uuid4()), "supersedes": target,
                         "modified-on": moment.isoformat(timespec="seconds")})
    else:
        title = moment.strftime("%Y-%m-%d %H:%M:%S")
        if any(section[lsf.TITLE] == title and not section[lsf.KEYS].get("supersedes") for section in document["sections"][1:]):
            return {"entry": None, "changed": False}  # Ignore duplicate creations in one second.
        section = {lsf.TITLE: title, lsf.KEYS: {"guid": str(uuid4()),
                   "date": moment.strftime("%Y-%m-%d"), "time": moment.strftime("%H:%M:%S")}, lsf.BODY: ""}
        keys = section[lsf.KEYS]
    keys.update({"hook": fields["hook"], "tags": fields["tags"],
                 "major": "true" if fields["major"] else "false", "indent": "2"})
    section[lsf.BODY] = encode_body(fields["body"])
    if target and request.get("overwrite"):
        document["sections"][document["sections"].index(source)] = section
    else:
        document["sections"].append(section)
    validate_document(document)
    return {"entry": read_entry(section), "changed": True}
