"""Coordinate the single netem root rule shared by both network APIs."""

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path


STATE_DIR = Path(__file__).resolve().parents[1] / ".dsfst"


class NetworkRuleError(Exception):
    pass


def _run(command: list[str], *, timeout: int, check: bool = True):
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=check, timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise NetworkRuleError(f"Network command failed: {exc}") from exc


def network_interface() -> str:
    configured = os.environ.get("DSFST_INTERFACE")
    if configured:
        return configured
    result = _run(["ip", "-o", "route", "show", "default"], timeout=5)
    words = result.stdout.split()
    if "dev" not in words or words.index("dev") + 1 >= len(words):
        raise NetworkRuleError("No default network interface found")
    return words[words.index("dev") + 1]


@contextmanager
def _locked_state():
    import fcntl

    STATE_DIR.mkdir(exist_ok=True)
    with (STATE_DIR / "network.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = STATE_DIR / "network-rule.json"
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
        except (OSError, ValueError):
            state = {}
        yield state
        path.write_text(json.dumps(state))


def _netem_active(interface: str) -> bool:
    result = _run(["tc", "qdisc", "show", "dev", interface], timeout=5)
    return any("netem" in line for line in result.stdout.splitlines())


def apply_rule(kind: str, value: int) -> dict:
    if kind not in ("latency", "packet_loss"):
        raise NetworkRuleError("Unknown network rule")
    interface = network_interface()
    with _locked_state() as state:
        active = _netem_active(interface)
        owner = state.get("kind") if active and state.get("interface") == interface else None
        if active and owner != kind:
            raise NetworkRuleError("Another network rule is active; reset it first")
        args = ["delay", f"{value}ms"] if kind == "latency" else ["loss", f"{value}%"]
        _run(
            ["sudo", "-n", "tc", "qdisc", "replace", "dev", interface,
             "root", "netem", *args],
            timeout=10,
        )
        state.update(kind=kind, interface=interface, value=value)
    return {"interface": interface, "kind": kind, "value": value}


def reset_rule(kind: str) -> dict:
    interface = network_interface()
    with _locked_state() as state:
        if not _netem_active(interface):
            state.clear()
            return {"message": "No network rule active"}
        if state.get("kind") != kind or state.get("interface") != interface:
            raise NetworkRuleError("This API does not own the active network rule")
        result = _run(
            ["sudo", "-n", "tc", "qdisc", "del", "dev", interface, "root"],
            check=False, timeout=10,
        )
        if result.returncode not in (0, 2):
            raise NetworkRuleError(f"tc reset failed: {result.stderr.strip() or result.returncode}")
        state.clear()
    return {"message": "Network conditions reset"}
