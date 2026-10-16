"""Machine addresses, stack ownership, and supervised permanent/dynamic workers."""

from queue import Queue
from threading import Event, RLock, Thread, current_thread, local, main_thread
from uuid import uuid4
import traceback

machines = {}  # Registry membership and lifecycle publication use machines_lock.
machine_kinds = {}  # Registered before workers start; kind -> handler table.
machines_lock = RLock()
thread_state = local()
fatal = Event()
shutdown_started = Event()


def initialize_machine_system():
    with machines_lock:
        if any(r["thread"] and r["thread"].is_alive() for r in machines.values()):
            raise RuntimeError("cannot reset live machines")
        machines.clear()
        machine_kinds.clear()
        fatal.clear()
        shutdown_started.clear()


def install_machine(details):
    with machines_lock:
        machines[details["name"]] = {
            "dynamic": False, **details, "inbox": Queue(), "current-stack": None,
            "thread": None, "running": False, "lifecycle": "starting", "continuation-frames": None,
        }


def install_machine_kind(kind, handlers):
    with machines_lock:
        machine_kinds[kind] = dict(handlers)


def get_machine_runtimes():
    with machines_lock:
        return list(machines.values())


def begin_shutdown():
    """Close creation after Core has drained its accepted operations."""
    with machines_lock:
        shutdown_started.set()
        for runtime in machines.values():
            if runtime["dynamic"]:
                runtime["inbox"].put(None)


def reap_exited_machines():
    """Only Main joins and removes exited dynamic addresses; never join live work."""
    if current_thread() is not main_thread():
        raise RuntimeError("only the main thread may reap workers")
    for runtime in get_machine_runtimes():
        if runtime["dynamic"] and runtime["lifecycle"] == "exited":
            runtime["thread"].join()
            with machines_lock:
                runtime["lifecycle"] = "reaped"
                if machines.get(runtime["name"]) is runtime:
                    del machines[runtime["name"]]


def claim_machine(name):
    with machines_lock:
        thread_state.runtime = machines[name]


def get_current_runtime():
    return thread_state.runtime


def start_worker(name, loop):
    with machines_lock:
        runtime = machines[name]
        if runtime["thread"] is not None:
            raise RuntimeError(f"worker already started: {name}")
        runtime["thread"] = Thread(target=run_worker, args=(name, loop), name=f"PyDeck {name}")
        runtime["thread"].start()


def when_thread_dies_unexpectedly():
    with machines_lock:
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
        with machines_lock:
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
        with machines_lock:
            runtime["lifecycle"] = "exited"


def request_machine_retirement():
    with machines_lock:
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
    with machines_lock:
        if fatal.is_set():
            runtime["current-stack"] = None
            return
        frame = work["frames"][-1]
        address = frame["machine"]
        if isinstance(address, dict):
            if shutdown_started.is_set():
                raise RuntimeError("cannot create a machine during shutdown")
            kind = address["new"]
            address = f"{kind}-{uuid4().hex}"
            install_machine({"name": address, "handlers": machine_kinds[kind], "dynamic": True})
            frame["machine"] = address
            start_worker(address, run_machine)
        destination = machines.get(address)
        if destination is None or destination["lifecycle"] in {"stopping", "exited", "reaped"}:
            if shutdown_started.is_set():
                runtime["current-stack"] = None
                return
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
