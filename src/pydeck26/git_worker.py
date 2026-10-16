"""Disposable Git machines: subprocesses and repository files never enter Tk/Disk.

Each instance owns its context through its runtime. No module-level working
register is shared between instances. Commands use argv and literal pathspecs.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import subprocess

from . import machine, mobile_stacks as ms

COMMAND_TIMEOUT = 120
TEXT_LIMIT = 2 * 1024 * 1024
STATUS_NAMES = {"M": "Modified", "A": "Added", "D": "Deleted", "R": "Renamed",
                "C": "Copied", "T": "Type changed", "U": "Conflict", "?": "Untracked"}


def context():
    return machine.get_current_runtime()["git-context"]


def run_git(arguments, flags=None):
    """Run argv, or an argv/input command record, without a shell or terminal."""
    input_data = None
    if isinstance(arguments, dict):
        input_data = arguments.get("input")
        arguments = arguments["argv"]
    environment = os.environ.copy()
    # An enclosing Git hook/editor must not redirect this project's commands.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(key, None)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never",
                        "GIT_EDITOR": "true", "GIT_SEQUENCE_EDITOR": "true",
                        "GIT_PAGER": "cat", "GIT_OPTIONAL_LOCKS": "0"})
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(
        ["git", "--no-pager", "--literal-pathspecs", *arguments], cwd=context()["root"],
        env=environment, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    try:
        output, error = process.communicate(input=input_data, timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.communicate()
        raise ValueError("Git timed out. Refresh the repository before retrying; the operation may have completed.")
    if process.returncode and "allow-failure" not in (flags or []):
        raise ValueError((error or output).decode("utf-8", "replace").strip() or "Git command failed.")
    return {"code": process.returncode, "output": output, "error": error}


def git_output(arguments):
    return run_git(arguments)["output"]


def has_head():
    return run_git(["rev-parse", "--verify", "HEAD"], ["allow-failure"])["code"] == 0


def checked_path(name):
    """Allow repository files, including symlinks themselves, never escaped parents."""
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or ".." in relative.parts
            or any(part.lower() == ".git" for part in relative.parts)
            or "\\" in name and os.name == "nt" or "\x00" in name
            or os.name == "nt" and ":" in name):
        raise ValueError("Invalid repository file path.")
    root = context()["root"]
    path = root.joinpath(*relative.parts)
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError("The file's parent is outside the repository.")
    return path


def get_file_stamp(name):
    try:
        info = checked_path(name).lstat()
        return [info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    except FileNotFoundError:
        return None


def digest(value):
    return hashlib.sha256(value).hexdigest()


def parse_numstat(output):
    """NUL paths are literal; renames carry a separate old/new path pair."""
    results = {}
    entries = iter(output.split(b"\0"))
    for entry in entries:
        if not entry:
            continue
        added, removed, name = entry.split(b"\t", 2)
        if not name:
            next(entries)  # Rename/copy source; the status row uses its destination.
            name = next(entries)
        binary = added == b"-" or removed == b"-"
        results[name.decode("utf-8", "surrogateescape")] = {
            "binary": binary, "added": None if binary else int(added),
            "removed": None if binary else int(removed),
        }
    return results


def get_untracked_diff(name):
    """A new text file is all additions; inspect links without following them."""
    path = checked_path(name)
    try:
        if path.is_symlink():
            data = os.fsencode(os.readlink(path))
            return {"binary": False, "added": data.count(b"\n") + int(bool(data) and not data.endswith(b"\n")), "removed": 0}
        if not stat.S_ISREG(path.stat().st_mode):
            return None
        with path.open("rb") as source:
            chunk = source.read(8192)
            if b"\0" in chunk:
                return {"binary": True, "added": None, "removed": None}
            lines, last = 0, b""
            while chunk:
                lines += chunk.count(b"\n")
                last = chunk[-1:]
                chunk = source.read(1024 * 1024)
        return {"binary": False, "added": lines + int(bool(last) and last != b"\n"), "removed": 0}
    except OSError:
        return None


def add_file_metrics(records, index_entries):
    """Staged size is the indexed blob; unstaged size is the working file."""
    objects = {}
    for record in records["staged"]:
        for entry in index_entries.get(record["path"], []):
            mode, oid, stage = entry.split()
            if stage == "0" and mode != "160000":
                objects[oid] = None
    if objects:
        output = git_output({"argv": ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                             "input": ("\n".join(objects) + "\n").encode("ascii")})
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[1] == b"blob":
                objects[fields[0].decode("ascii")] = int(fields[2])
    for side in ("staged", "unstaged"):
        tracked = [record for record in records[side] if record["code"] != "?"]
        arguments = ["diff", "--numstat", "-z", "--no-ext-diff", "--no-textconv"]
        if side == "staged":
            arguments.append("--cached")
        changes = parse_numstat(git_output(arguments)) if tracked else {}
        for record in records[side]:
            record["size-bytes"] = None
            record["diff"] = None
            if record["submodule"]:
                continue
            if side == "staged":
                entries = index_entries.get(record["path"], [])
                record["size-bytes"] = (objects.get(entries[0].split()[1]) if entries else 0) if not record["conflict"] else None
            else:
                info = get_file_stamp(record["path"])
                if info is None:
                    record["size-bytes"] = 0
                elif stat.S_ISREG(info[0]) or stat.S_ISLNK(info[0]):
                    record["size-bytes"] = info[1]
            if not record["conflict"]:
                record["diff"] = get_untracked_diff(record["path"]) if record["code"] == "?" else changes.get(record["path"])


def read_status():
    output = git_output(["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    index = git_output(["ls-files", "--stage", "-z"])
    index_entries = {}
    for entry in index.split(b"\0"):
        if entry:
            details, name = entry.split(b"\t", 1)
            index_entries.setdefault(name.decode("utf-8", "surrogateescape"), []).append(details.decode("ascii"))
    head = run_git(["rev-parse", "--verify", "HEAD"], ["allow-failure"])
    branch = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], ["allow-failure"])
    branch_name = branch["output"].decode("utf-8", "replace").strip() or "Detached HEAD"
    upstream = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], ["allow-failure"])
    upstream_name = upstream["output"].decode("utf-8", "replace").strip() if not upstream["code"] else None
    ahead, behind = 0, 0
    if upstream_name:
        counts = git_output(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]).split()
        ahead, behind = map(int, counts)
    records = {"staged": [], "unstaged": []}
    entries = iter(output.split(b"\0"))
    for entry in entries:
        if not entry:
            continue
        xy, name = entry[:2].decode("ascii"), entry[3:].decode("utf-8", "surrogateescape")
        original = next(entries).decode("utf-8", "surrogateescape") if "R" in xy or "C" in xy else None
        stamp = digest(json.dumps([xy, original, index_entries.get(name), index_entries.get(original),
                                   get_file_stamp(name), get_file_stamp(original) if original else None],
                                  ensure_ascii=True).encode())
        conflict = xy in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
        for side, code in (("staged", xy[0]), ("unstaged", xy[1])):
            if code == " " or xy == "??" and side == "staged":
                continue
            records[side].append({"path": name, "old-path": original, "code": code,
                                  "label": "Conflict" if conflict else STATUS_NAMES.get(code, code),
                                  "conflict": conflict, "stamp": stamp, "rename": "R" in xy,
                                  "submodule": any(value.startswith("160000 ") for value in index_entries.get(name, []))})
    add_file_metrics(records, index_entries)
    return {"root": str(context()["root"]), "branch": branch_name, "upstream": upstream_name,
            "ahead": ahead, "behind": behind, "has-head": head["code"] == 0,
            "index-stamp": digest(head["output"] + index), **records}


def get_selected_records(request, snapshot):
    side = request["side"]
    if side not in ("staged", "unstaged"):
        raise ValueError("Unknown repository column.")
    current = {item["path"]: item for item in snapshot[side]}
    expected = request.get("records", [])
    if not expected:
        raise ValueError("Select at least one file.")
    for record in expected:
        if record != current.get(record["path"]):
            raise ValueError("Selected files changed since they were displayed. Refresh and review them again.")
    return expected


def get_record_paths(records):
    paths = []
    for record in records:
        for name in (record["path"], record["old-path"] if record["rename"] else None):
            if name and name not in paths:
                checked_path(name)
                paths.append(name)
    return paths


def require_plain_files(paths):
    for name in paths:
        path = checked_path(name)
        if path.is_dir() and not path.is_symlink():
            raise ValueError("Directories and submodules cannot be deleted or discarded from this panel.")


def read_text_file(name):
    path = checked_path(name)
    if path.is_symlink():
        return f"Symbolic link → {os.readlink(path)}"
    with path.open("rb") as source:
        data = source.read(TEXT_LIMIT + 1)
    if len(data) > TEXT_LIMIT:
        raise ValueError("This file is too large for the text viewer (limit: 2 MiB). Use Open File.")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeError:
            pass
    if b"\0" in data or any(byte < 9 or 13 < byte < 32 for byte in data):
        raise ValueError("This is a binary file. Use Open File to view it in its usual application.")
    try:
        return data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeError:
        return data.decode("cp1252", "replace").replace("\r\n", "\n").replace("\r", "\n")


def perform_request(request):
    operation = request["operation"]
    if operation not in {"status", "refresh", "stage", "unstage", "revert", "discard", "commit", "push", "file", "diff", "open"}:
        raise ValueError("Unknown Git operation.")
    snapshot = read_status()
    result = {"message": "Repository refreshed.", "viewer": None, "open-path": None}
    if operation == "refresh" and snapshot["upstream"]:
        remote = git_output(["config", "--get", f"branch.{snapshot['branch']}.remote"]).decode("utf-8", "replace").strip()
        run_git(["fetch", "--", remote])
    elif operation in {"stage", "unstage", "revert", "discard"}:
        expected_side = "staged" if operation in {"unstage", "discard"} else "unstaged"
        if request["side"] != expected_side:
            raise ValueError("This operation belongs to the other column.")
        records = get_selected_records(request, snapshot)
        paths = get_record_paths(records)
        if operation in {"revert", "discard"}:
            if any(record["submodule"] for record in records):
                raise ValueError("Submodules cannot be deleted or discarded from this panel.")
            require_plain_files(paths)
        if operation == "stage":
            run_git(["add", "-A", "--", *paths])
        elif operation == "unstage":
            if snapshot["has-head"]:
                run_git(["restore", "--source=HEAD", "--staged", "--", *paths])
            else:
                run_git(["rm", "--cached", "-f", "--", *paths])
        elif operation == "revert":
            if any(record["conflict"] for record in records):
                raise ValueError("Resolve merge conflicts before reverting files.")
            # Untracked paths may still exist in HEAD after a staged deletion.
            committed = set(git_output(["ls-tree", "-r", "--name-only", "-z", "HEAD", "--", *paths])
                            .decode("utf-8", "surrogateescape").split("\0")) if snapshot["has-head"] else set()
            untracked = {record["path"] for record in records if record["code"] == "?"}
            restore = [name for name in paths if name not in untracked or name in committed]
            if restore:
                if snapshot["has-head"]:
                    run_git(["restore", "--source=HEAD", "--staged", "--worktree", "--", *restore])
                else:
                    run_git(["rm", "--cached", "-f", "--", *restore])
                    for name in restore:
                        checked_path(name).unlink(missing_ok=True)
            for name in untracked - committed:
                checked_path(name).unlink(missing_ok=True)
        else:
            if any(record["conflict"] for record in records):
                raise ValueError("Resolve merge conflicts before discarding staged files.")
            if snapshot["has-head"]:
                run_git(["restore", "--source=HEAD", "--staged", "--worktree", "--", *paths])
            else:
                run_git(["rm", "--cached", "-f", "--", *paths])
                for name in paths:
                    checked_path(name).unlink(missing_ok=True)
        result["message"] = {"stage": "Selected files staged.", "unstage": "Selected files unstaged.",
                             "revert": "Selected files reverted to the last commit; files with no committed version deleted.", "discard": "Selected staged and working changes discarded."}[operation]
    elif operation == "commit":
        message = request.get("message", "").strip()
        if not message:
            raise ValueError("Enter a commit message.")
        if not snapshot["staged"]:
            raise ValueError("There are no staged changes to commit.")
        if snapshot["index-stamp"] != request.get("index-stamp"):
            raise ValueError("Staged changes changed. Refresh and review them before committing.")
        result["message"] = git_output(["commit", "-m", message]).decode("utf-8", "replace").strip()
    elif operation == "push":
        if not snapshot["upstream"]:
            raise ValueError("This branch has no upstream. Configure one before using Push.")
        if snapshot["behind"] or not snapshot["ahead"]:
            raise ValueError("Push is available when this branch is ahead of upstream without being behind.")
        response = run_git(["push"])
        result["message"] = (response["output"] + response["error"]).decode("utf-8", "replace").strip() or "Pushed."
    elif operation in {"file", "diff", "open"}:
        record = request["record"]
        name = record["path"]
        path = checked_path(name)
        if operation == "open":
            if not path.exists():
                raise ValueError("That file no longer exists on disk.")
            result["open-path"] = str(path)
        else:
            if operation == "file":
                text = read_text_file(name)
            elif record["code"] == "?":
                text = "Untracked file (not yet in the index):\n\n" + read_text_file(name)
            else:
                arguments = ["diff", "--no-ext-diff", "--no-textconv", "--no-color"]
                if request["side"] == "staged":
                    arguments.append("--cached")
                text = git_output([*arguments, "--", *get_record_paths([record])]).decode("utf-8", "replace")
                if len(text.encode("utf-8")) > TEXT_LIMIT:
                    raise ValueError("This diff is too large for the text viewer (limit: 2 MiB).")
                text = text or "No textual differences are available for this file."
            result["viewer"] = {"title": f"{'Diff' if operation == 'diff' else 'File'}: {name}", "text": text}
    return result


def handle_when_git_operation_requested():
    machine.get_current_runtime()["git-context"] = {"root": Path(ms.get_register("project-root")).resolve()}
    result = {"ok": False, "message": "", "snapshot": None, "viewer": None, "open-path": None}
    try:
        root = git_output(["rev-parse", "--show-toplevel"]).decode("utf-8", "surrogateescape").strip()
        context()["root"] = Path(root).resolve()
        result.update(perform_request(ms.get_register("git-request")))
        result["ok"] = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result["message"] = str(error)
    # Even a failed hook/fetch may have changed the index or refs. Return fresh state.
    try:
        result["snapshot"] = read_status()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    ms.set_register(("git-result", result))
    machine.request_machine_retirement()


HANDLERS = {"OPERATE": handle_when_git_operation_requested}
