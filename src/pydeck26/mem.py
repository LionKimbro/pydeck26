"""Mem machine: canonical project records and revisioned commits."""

from copy import deepcopy

from . import captains_log, machine, mobile_stacks as ms, workspace

g = {"revision": 0, "initialized": False}
documents = {}  # Canonical; no other machine receives aliases.


def handle_when_mem_installs_project_bundle():
    bundle = ms.get_register("bundle")
    if bundle["workspace"] is None:
        bundle["workspace"] = workspace.make_default_workspace()
    workspace.validate_workspace(bundle["workspace"])
    captains_log.validate_document(bundle["captains-log"])
    documents.clear()
    documents.update(deepcopy({key: bundle[key] for key in (
        "whiteboard", "dictionary", "conversations", "ideas", "resources", "workspace", "captains-log",
    )}))
    g["initialized"] = bundle["initialized"]
    g["revision"] = 0
    ms.set_register(("bundle", deepcopy(bundle)))
    ms.set_register(("revision", g["revision"]))


def handle_when_mem_accepts_project_commit():
    if not g["initialized"]:
        raise RuntimeError("cannot commit an uninitialized project")
    if ms.get_register("base-revision") != g["revision"]:
        raise RuntimeError("canonical project revision conflict")
    proposal = deepcopy(ms.get_register("documents"))
    if "workspace" in proposal:
        workspace.validate_workspace(proposal["workspace"])
    if "captains-log" in proposal:
        captains_log.validate_document(proposal["captains-log"])
    documents.update(proposal)
    g["revision"] += 1
    ms.set_register(("revision", g["revision"]))
    ms.set_register(("documents", deepcopy(proposal)))
    # Mem owns persistence scheduling. Runtime pops this handler before Disk runs.
    machine.continue_with_frames([{"machine": "DISK", "entry": "WRITE_DOCUMENTS"}])


HANDLERS = {
    "INSTALL_PROJECT": handle_when_mem_installs_project_bundle,
    "COMMIT_PROJECT": handle_when_mem_accepts_project_commit,
}
