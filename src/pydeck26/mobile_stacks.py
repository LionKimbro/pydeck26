"""Bottom-first continuation frames and explicit traveling registers."""

from . import machine


def stack():
    return machine.get_current_runtime()["current-stack"]


def create_stack():
    if stack() is not None:
        raise RuntimeError("another stack is already active")
    machine.get_current_runtime()["current-stack"] = {
        "kind": "MOBILE_STACK", "frames": [], "registers": {},
    }


def push_frame(frame):
    stack()["frames"].append(frame)


def set_register(pair):
    key, value = pair
    stack()["registers"][key] = value


def get_register(key):
    return stack()["registers"][key]


def is_mobile_stack(item):
    return isinstance(item, dict) and item.get("kind") == "MOBILE_STACK"

