"""Real Git repositories exercise worker ownership, index semantics, and pushes."""

from queue import Empty
import subprocess
from threading import Event, current_thread
from time import monotonic

import pytest

from pydeck26 import git_core, git_worker, machine, main, workspace
from pydeck26.storage import initialize_project


def git(root, arguments):
    result = subprocess.run(["git", *arguments], cwd=root, capture_output=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout.decode("utf-8", "replace")


def setup_repository(root, flags=None):
    root.mkdir(exist_ok=True)
    git(root, ["init", "--initial-branch=main"])
    git(root, ["config", "user.name", "Panel Test"])
    git(root, ["config", "user.email", "panel@example.invalid"])
    git(root, ["config", "commit.gpgsign", "false"])
    git(root, ["config", "core.hooksPath", str(root / "no-hooks")])
    (root / ".gitignore").write_text("db/\ndocs/\n", encoding="utf-8")
    (root / "tracked.txt").write_text("first\nsecond\n", encoding="utf-8")
    if "unborn" not in (flags or []):
        git(root, ["add", ".gitignore", "tracked.txt"])
        git(root, ["commit", "-m", "Initial"])


def receive(commands, predicate):
    deadline = monotonic() + 12
    while monotonic() < deadline:
        assert not machine.fatal.is_set(), "worker failed"
        try:
            command = commands.get(timeout=0.05)
        except Empty:
            continue
        if predicate(command):
            return command
    pytest.fail("timed out waiting for Git result")


def send(event):
    machine.machines["CORE"]["inbox"].put(event)


def request(commands, operation, **details):
    send({"type": "GIT_REQUEST", "operation": operation, "revision": git_core.g["revision"], **details})
    return receive(commands, lambda item: item["type"] == "GIT_STATE" and not item["busy"])


@pytest.fixture
def repository(tmp_path):
    setup_repository(tmp_path)
    initialize_project(tmp_path)
    commands = main.start_project_workers(tmp_path)
    receive(commands, lambda item: item["type"] == "STATE" and item["ready"])
    yield tmp_path, commands
    if machine.machines["CORE"]["thread"].is_alive() and not machine.fatal.is_set():
        send({"type": "SHUTDOWN"})
        receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
    main.finish_worker_shutdown()


def test_partial_staging_diff_unstage_commit_and_thread_ownership(repository, monkeypatch):
    root, commands = repository
    observed = []
    original = git_worker.run_git

    def observe(arguments, flags=None):
        observed.append(current_thread().name)
        return original(arguments, flags)

    monkeypatch.setattr(git_worker, "run_git", observe)
    (root / "tracked.txt").write_text("staged\nsecond\n")
    git(root, ["add", "tracked.txt"])
    (root / "tracked.txt").write_text("staged\nunstaged\n")
    state = request(commands, "status")
    assert state["snapshot"]["staged"][0]["path"] == "tracked.txt"
    assert state["snapshot"]["unstaged"][0]["path"] == "tracked.txt"
    staged = request(commands, "diff", side="staged", paths=["tracked.txt"])
    assert "+staged" in staged["viewer"]["text"] and "+unstaged" not in staged["viewer"]["text"]
    unstaged = request(commands, "diff", side="unstaged", paths=["tracked.txt"])
    assert "+unstaged" in unstaged["viewer"]["text"]
    assert request(commands, "unstage", side="staged", paths=["tracked.txt"])["ok"]
    assert git(root, ["diff", "--cached"]) == ""
    assert request(commands, "stage", side="unstaged", paths=["tracked.txt"])["ok"]
    result = request(commands, "commit", message='Message with "quotes" and $(literal)')
    assert result["ok"], result
    assert git(root, ["log", "-1", "--format=%s"]).strip() == 'Message with "quotes" and $(literal)'
    assert not result["snapshot"]["staged"]
    assert observed and all(name.startswith("PyDeck GIT-") for name in observed)
    # Main alone reaps dynamic threads, leaving permanent machine addresses intact.
    for runtime in machine.get_machine_runtimes():
        if runtime["dynamic"]:
            runtime["thread"].join(2)
    machine.reap_exited_machines()
    assert set(machine.machines) == {"CORE", "MEM", "DISK", "IMAGE"}


def test_stale_revert_is_rejected_and_revert_restores_last_commit(repository):
    root, commands = repository
    (root / "tracked.txt").write_text("staged\n")
    git(root, ["add", "tracked.txt"])
    (root / "tracked.txt").write_text("newer\n")
    request(commands, "status")
    (root / "tracked.txt").write_text("newer edits after confirmation\n")
    result = request(commands, "revert", side="unstaged", paths=["tracked.txt"])
    assert not result["ok"] and "changed" in result["message"]
    assert (root / "tracked.txt").exists()
    result = request(commands, "revert", side="unstaged", paths=["tracked.txt"])
    assert result["ok"], result
    assert (root / "tracked.txt").read_text() == "first\nsecond\n"
    assert git(root, ["show", ":tracked.txt"]) == git(root, ["show", "HEAD:tracked.txt"])
    assert not result["snapshot"]["staged"] and not result["snapshot"]["unstaged"]


@pytest.mark.parametrize("change", ["modified", "deleted", "staged-deletion", "staged-addition"])
def test_revert_mixed_selection_restores_committed_files_and_deletes_new_files(repository, change):
    root, commands = repository
    if change == "deleted":
        (root / "tracked.txt").unlink()
    elif change == "staged-deletion":
        git(root, ["rm", "tracked.txt"])
        (root / "tracked.txt").write_text("recreated\n")
    elif change == "staged-addition":
        (root / "tracked.txt").write_text("modified\n")
        (root / "added.txt").write_text("staged\n")
        git(root, ["add", "added.txt"])
        (root / "added.txt").write_text("unstaged\n")
    else:
        (root / "tracked.txt").write_text("modified\n")
    (root / "[new].txt").write_text("new file\n")
    (root / "keep.txt").write_text("keep me\n")
    paths = ["tracked.txt", "[new].txt"] + (["added.txt"] if change == "staged-addition" else [])
    request(commands, "status")
    result = request(commands, "revert", side="unstaged", paths=paths)
    assert result["ok"], result
    assert (root / "tracked.txt").read_text() == "first\nsecond\n"
    assert not (root / "[new].txt").exists()
    assert not (root / "added.txt").exists()
    assert (root / "keep.txt").read_text() == "keep me\n"
    assert not result["snapshot"]["staged"]
    assert [item["path"] for item in result["snapshot"]["unstaged"]] == ["keep.txt"]


def test_rename_added_files_and_literal_pathspecs(repository):
    root, commands = repository
    git(root, ["mv", "tracked.txt", "renamed file.txt"])
    result = request(commands, "status")
    record = result["snapshot"]["staged"][0]
    assert record["code"] == "R" and record["old-path"] == "tracked.txt"
    assert record["diff"] == {"binary": False, "added": 0, "removed": 0}
    assert record["size-bytes"] == int(git(root, ["cat-file", "-s", "HEAD:tracked.txt"]))
    result = request(commands, "discard", side="staged", paths=["renamed file.txt"])
    assert result["ok"], result
    assert (root / "tracked.txt").exists() and not (root / "renamed file.txt").exists()
    names = ["[literal].txt", "other.txt", "文書.txt", "-option.txt"]
    for name in names:
        (root / name).write_text("new file\n", encoding="utf-8")
    request(commands, "status")
    result = request(commands, "stage", side="unstaged", paths=[names[0], names[2], names[3]])
    assert result["ok"], result
    assert {item["path"] for item in result["snapshot"]["staged"]} == {names[0], names[2], names[3]}
    result = request(commands, "discard", side="staged", paths=[names[0]])
    assert result["ok"] and not (root / names[0]).exists()
    assert (root / names[1]).exists()


def test_file_binary_and_failed_commit_results(repository):
    root, commands = repository
    (root / "binary.bin").write_bytes(b"\0\1binary")
    request(commands, "status")
    result = request(commands, "file", side="unstaged", paths=["binary.bin"])
    assert not result["ok"] and "binary" in result["message"]
    (root / "tracked.txt").write_text("working\n")
    request(commands, "status")
    result = request(commands, "file", side="unstaged", paths=["tracked.txt"])
    assert result["viewer"]["text"] == "working\n"
    result = request(commands, "open", side="unstaged", paths=["tracked.txt"])
    assert result["ok"]
    request(commands, "stage", side="unstaged", paths=["tracked.txt"])
    # A genuine failed Git commit, without invoking platform-specific hook scripts.
    git(root, ["config", "user.name", ""])
    git(root, ["config", "user.email", ""])
    result = request(commands, "commit", message="Keep my draft")
    assert not result["ok"] and result["committed-message"] == "Keep my draft"
    assert result["snapshot"]["staged"]


def test_push_and_refresh_against_local_bare_remote(repository, tmp_path):
    root, commands = repository
    remote = tmp_path.parent / f"{tmp_path.name}-remote.git"
    git(root, ["init", "--bare", str(remote)])
    # Keep the disposable remote outside the repository being inspected.
    git(root, ["remote", "add", "origin", str(remote)])
    git(root, ["push", "-u", "origin", "main"])
    state = request(commands, "refresh")
    assert state["ok"] and state["snapshot"]["ahead"] == state["snapshot"]["behind"] == 0
    (root / "tracked.txt").write_text("push me\n")
    request(commands, "status")
    request(commands, "stage", side="unstaged", paths=["tracked.txt"])
    state = request(commands, "commit", message="Push test")
    assert state["ok"] and state["snapshot"]["ahead"] == 1
    state = request(commands, "push")
    assert state["ok"], state
    assert state["snapshot"]["ahead"] == state["snapshot"]["behind"] == 0
    assert git(root, ["rev-parse", "HEAD"]) == git(remote, ["rev-parse", "refs/heads/main"])
    assert not request(commands, "push")["ok"]
    other = tmp_path.parent / f"{tmp_path.name}-other"
    git(root, ["clone", "--branch", "main", str(remote), str(other)])
    for key, value in (("user.name", "Other"), ("user.email", "other@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(other / "no-hooks"))):
        git(other, ["config", key, value])
    (other / "tracked.txt").write_text("remote change\n")
    git(other, ["commit", "-am", "Remote change"])
    git(other, ["push"])
    state = request(commands, "refresh")
    assert state["ok"] and state["snapshot"]["behind"] == 1
    assert not request(commands, "push")["ok"]
    (root / "tracked.txt").write_text("local divergent change\n")
    request(commands, "status")
    request(commands, "stage", side="unstaged", paths=["tracked.txt"])
    state = request(commands, "commit", message="Diverge")
    assert state["snapshot"]["ahead"] == state["snapshot"]["behind"] == 1
    assert not request(commands, "push")["ok"]


def test_external_index_change_prevents_commit(repository):
    root, commands = repository
    (root / "tracked.txt").write_text("staged\n")
    git(root, ["add", "tracked.txt"])
    request(commands, "status")
    (root / "extra.txt").write_text("Added by another application\n")
    git(root, ["add", "extra.txt"])
    result = request(commands, "commit", message="Do not commit unseen changes")
    assert not result["ok"] and "Staged changes changed" in result["message"]
    assert git(root, ["log", "-1", "--format=%s"]).strip() == "Initial"


def test_file_sizes_and_diff_counts_match_each_side_of_the_index(repository):
    root, commands = repository
    git(root, ["config", "core.autocrlf", "false"])
    (root / "counts.txt").write_bytes(b"one\ntwo\n")
    git(root, ["add", "counts.txt"])
    git(root, ["commit", "-m", "Count baseline"])
    staged_bytes = b"one\nstaged\nthree\n"
    working_bytes = b"one\nstaged\nworking\n"
    (root / "counts.txt").write_bytes(staged_bytes)
    git(root, ["add", "counts.txt"])
    (root / "counts.txt").write_bytes(working_bytes)
    (root / "new.txt").write_bytes(b"a\nb")
    (root / "empty.txt").write_bytes(b"")
    (root / "binary.bin").write_bytes(b"\0\1\2\3")
    state = request(commands, "status")
    staged = {item["path"]: item for item in state["snapshot"]["staged"]}
    unstaged = {item["path"]: item for item in state["snapshot"]["unstaged"]}
    assert staged["counts.txt"]["size-bytes"] == len(staged_bytes)
    assert unstaged["counts.txt"]["size-bytes"] == len(working_bytes)
    assert staged["counts.txt"]["diff"] == {"binary": False, "added": 2, "removed": 1}
    assert unstaged["counts.txt"]["diff"] == {"binary": False, "added": 1, "removed": 1}
    assert unstaged["new.txt"]["diff"] == {"binary": False, "added": 2, "removed": 0}
    assert unstaged["empty.txt"]["size-bytes"] == 0
    assert unstaged["empty.txt"]["diff"] == {"binary": False, "added": 0, "removed": 0}
    assert unstaged["binary.bin"]["size-bytes"] == 4
    assert unstaged["binary.bin"]["diff"]["binary"]
    state = request(commands, "stage", side="unstaged", paths=["new.txt", "binary.bin"])
    staged = {item["path"]: item for item in state["snapshot"]["staged"]}
    assert staged["new.txt"]["size-bytes"] == 3
    assert staged["binary.bin"]["diff"]["binary"]
    (root / "counts.txt").unlink()
    state = request(commands, "status")
    removed = next(item for item in state["snapshot"]["unstaged"] if item["path"] == "counts.txt")
    assert removed["size-bytes"] == 0
    assert removed["diff"] == {"binary": False, "added": 0, "removed": 3}
    state = request(commands, "stage", side="unstaged", paths=["counts.txt"])
    removed = next(item for item in state["snapshot"]["staged"] if item["path"] == "counts.txt")
    assert removed["size-bytes"] == 0
    assert removed["diff"] == {"binary": False, "added": 0, "removed": 2}


def test_numstat_parser_preserves_literal_paths_and_rename_pairs():
    result = git_worker.parse_numstat(b"1\t2\tname\twith\ttabs\0" + b"0\t0\t\0old name\0new name\0" + b"-\t-\tbinary\0")
    assert result["name\twith\ttabs"] == {"binary": False, "added": 1, "removed": 2}
    assert result["new name"] == {"binary": False, "added": 0, "removed": 0}
    assert result["binary"]["binary"]


def test_close_waits_for_git_operation_and_dynamic_creation_is_closed(repository, monkeypatch):
    root, commands = repository
    entered, release = Event(), Event()
    original = git_worker.HANDLERS["OPERATE"]

    def held_operation():
        entered.set()
        assert release.wait(5)
        original()

    monkeypatch.setitem(git_worker.HANDLERS, "OPERATE", held_operation)
    # Kinds are passive copies installed before workers start; replace this test kind explicitly.
    machine.install_machine_kind("GIT", git_worker.HANDLERS)
    send({"type": "GIT_REQUEST", "operation": "status"})
    assert entered.wait(5)
    send({"type": "SHUTDOWN"})
    assert not machine.shutdown_started.is_set()
    assert machine.machines["CORE"]["thread"].is_alive()
    release.set()
    receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
    assert machine.shutdown_started.is_set()


def test_unborn_unstage_and_discard(tmp_path):
    setup_repository(tmp_path, ["unborn"])
    initialize_project(tmp_path)
    commands = main.start_project_workers(tmp_path)
    receive(commands, lambda item: item["type"] == "STATE" and item["ready"])
    try:
        git(tmp_path, ["add", "tracked.txt"])
        request(commands, "status")
        result = request(commands, "unstage", side="staged", paths=["tracked.txt"])
        assert result["ok"] and (tmp_path / "tracked.txt").exists()
        request(commands, "stage", side="unstaged", paths=["tracked.txt"])
        result = request(commands, "discard", side="staged", paths=["tracked.txt"])
        assert result["ok"] and not (tmp_path / "tracked.txt").exists()
    finally:
        send({"type": "SHUTDOWN"})
        receive(commands, lambda item: item["type"] == "SHUTDOWN_COMPLETE")
        main.finish_worker_shutdown()


def test_git_is_an_optional_hostable_project_panel():
    document = workspace.make_default_workspace()
    assert "project-git" not in document["panels"]
    workspace.apply_layout_event(document, {"type": "CREATE_PROJECT_PANEL", "panel-type": "GIT", "position-id": "overview/column-1"})
    workspace.validate_workspace(document)
    assert document["positions"]["overview/column-1"]["panel-id"] == "project-git"
