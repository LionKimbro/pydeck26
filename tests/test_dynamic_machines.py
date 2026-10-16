"""Creation addresses, multi-hop continuations, retirement, and fatal supervision."""

from threading import Event

import pytest

from pydeck26 import machine, mobile_stacks as ms


def test_dynamic_instance_waits_for_return_then_retires_and_is_reaped():
    machine.initialize_machine_system()
    observed = []

    def start():
        address = machine.get_current_runtime()["name"]
        observed.append(address)
        ms.set_register(("value", 1))
        machine.continue_with_frames([{"machine": address, "entry": "RETURN"},
                                      {"machine": "RELAY", "entry": "BOUNCE"}])

    def bounce():
        ms.set_register(("value", ms.get_register("value") + 1))

    def returned():
        assert ms.get_register("value") == 2
        machine.request_machine_retirement()

    machine.install_machine({"name": "SOURCE", "handlers": {}})
    machine.install_machine({"name": "RELAY", "handlers": {"BOUNCE": bounce}})
    machine.install_machine_kind("TEMP", {"START": start, "RETURN": returned})
    machine.start_worker("RELAY", machine.run_machine)
    machine.claim_machine("SOURCE")
    try:
        for unused in range(3):
            ms.create_stack()
            ms.push_frame({"machine": "SOURCE", "entry": "DONE"})
            creation = {"machine": {"new": "TEMP"}, "entry": "START"}
            ms.push_frame(creation)
            machine.route_current_stack()
            work = machine.machines["SOURCE"]["inbox"].get(timeout=3)
            assert work["registers"]["value"] == 2
            assert isinstance(creation["machine"], str)
            runtime = machine.machines[creation["machine"]]
            runtime["thread"].join(3)
            assert runtime["lifecycle"] == "exited"
            machine.reap_exited_machines()
            assert creation["machine"] not in machine.machines
        assert len(set(observed)) == 3
        assert not machine.fatal.is_set()
        machine.begin_shutdown()
        ms.create_stack()
        ms.push_frame({"machine": {"new": "TEMP"}, "entry": "START"})
        with pytest.raises(RuntimeError, match="during shutdown"):
            machine.route_current_stack()
    finally:
        machine.machines["RELAY"]["inbox"].put(None)
        machine.join_machine("RELAY")


def test_dynamic_failure_uses_the_same_fatal_boundary():
    machine.initialize_machine_system()
    entered = Event()

    def fail():
        entered.set()
        raise RuntimeError("injected dynamic failure")

    machine.install_machine({"name": "SOURCE", "handlers": {}})
    machine.install_machine({"name": "IDLE", "handlers": {}})
    machine.install_machine_kind("FAIL", {"RUN": fail})
    machine.start_worker("IDLE", machine.run_machine)
    machine.claim_machine("SOURCE")
    ms.create_stack()
    ms.push_frame({"machine": {"new": "FAIL"}, "entry": "RUN"})
    machine.route_current_stack()
    assert entered.wait(3)
    assert machine.fatal.wait(3)
    for runtime in machine.get_machine_runtimes():
        if runtime["thread"]:
            runtime["thread"].join(3)
            assert not runtime["thread"].is_alive()
    machine.reap_exited_machines()
    assert set(machine.machines) == {"SOURCE", "IDLE"}
