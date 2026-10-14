"""Mem machine: canonical project records and revisioned commits."""

from copy import deepcopy

from . import machine, mobile_stacks as ms

g = {"revision": 0, "initialized": False}
documents = {}  # Canonical; no other machine receives aliases.


def handle_when_mem_installs_project_bundle():
    bundle = ms.get_register("bundle")
    documents.clear()
    documents.update(deepcopy({key: bundle[key] for key in (
        "whiteboard", "dictionary", "conversations", "ideas", "resources",
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
