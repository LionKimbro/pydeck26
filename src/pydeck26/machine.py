"""Permanent machine runtimes, stack ownership, and supervised worker lifetimes."""

from queue import Queue
from threading import Event, Thread, current_thread, local, main_thread
import traceback

machines = {}  # Installed before startup; main marks joined workers as reaped.
thread_state = local()
fatal = Event()
shutdown_started = Event()


def initialize_machine_system():
    if any(r["thread"] and r["thread"].is_alive() for r in machines.values()):
        raise RuntimeError("cannot reset live machines")
    machines.clear()
    fatal.clear()
    shutdown_started.clear()


def install_machine(details):
    machines[details["name"]] = {
        **details, "inbox": Queue(), "current-stack": None,
        "thread": None, "running": False, "lifecycle": "starting", "continuation-frames": None,
    }


def claim_machine(name):
    thread_state.runtime = machines[name]


def get_current_runtime():
    return thread_state.runtime


def start_worker(name, loop):
    runtime = machines[name]
    if runtime["thread"] is not None:
        raise RuntimeError(f"worker already started: {name}")
    runtime["thread"] = Thread(target=run_worker, args=(name, loop), name=f"PyDeck {name}")
    runtime["thread"].start()


def when_thread_dies_unexpectedly():
    if fatal.is_set():
        return
    fatal.set()
    shutdown_started.set()
    for runtime in machines.values():
        runtime["inbox"].put(None)


def run_worker(name, loop):
    claim_machine(name)
    runtime = get_current_runtime()
    try:
        if fatal.is_set():
            return
        runtime["lifecycle"] = "running"
        runtime["running"] = True
        loop()
        if runtime["running"] and not fatal.is_set():
            raise RuntimeError(f"{name} returned without retirement")
    except BaseException:
        traceback.print_exc()
        when_thread_dies_unexpectedly()
    finally:
        runtime["running"] = False
        runtime["current-stack"] = None
        runtime["continuation-frames"] = None
        runtime["lifecycle"] = "exited"


def request_machine_retirement():
    runtime = get_current_runtime()
    runtime["lifecycle"] = "stopping"
    runtime["running"] = False


def handle_received_mobile_stack(work):
    runtime = get_current_runtime()
    if runtime["current-stack"] is not None:
        raise RuntimeError("cannot replace an active stack")
    runtime["current-stack"] = work
    frame = work["frames"][-1]
    if frame["machine"] != runtime["name"]:
        raise RuntimeError("stack delivered to the wrong machine")
    runtime["handlers"][frame["entry"]]()
    work["frames"].pop()
    if runtime["continuation-frames"] is not None:
        work["frames"].extend(runtime["continuation-frames"])
        runtime["continuation-frames"] = None
    if work["frames"]:
        route_current_stack()
    else:
        runtime["current-stack"] = None


def continue_with_frames(frames):
    """Declare a continuation; runtime completes the current frame first."""
    runtime = get_current_runtime()
    if runtime["continuation-frames"] is not None:
        raise RuntimeError("continuation already specified")
    runtime["continuation-frames"] = list(frames)


def route_current_stack():
    runtime = get_current_runtime()
    work = runtime["current-stack"]
    destination = machines[work["frames"][-1]["machine"]]
    if fatal.is_set():
        runtime["current-stack"] = None
        return
    if destination["lifecycle"] in {"stopping", "exited", "reaped"}:
        raise RuntimeError("cannot route to a retired machine")
    runtime["current-stack"] = None  # Transfer ownership before publication.
    destination["inbox"].put(work)


def run_machine():
    runtime = get_current_runtime()
    while runtime["running"] and not fatal.is_set():
        item = runtime["inbox"].get()
        if item is None or fatal.is_set():
            request_machine_retirement()
            return
        handle_received_mobile_stack(item)
    request_machine_retirement()


def join_machine(name):
    if current_thread() is not main_thread():
        raise RuntimeError("only the main thread may join and reap workers")
    runtime = machines[name]
    runtime["thread"].join()
    runtime["lifecycle"] = "reaped"
