"""Compatibility entrypoint for the project-bound cockpit."""

from lionscliapp.execroot import get_execroot

from .main import run_project


def launch_cockpit() -> None:
    run_project(get_execroot())
