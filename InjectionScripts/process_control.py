"""Stop the stress process and its own workers before confirming a reset."""
import os
import signal
import subprocess
import psutil


def _running(process):
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def stop_owned_process(process):
    if process is None:
        return False
    active = process.poll() is None
    children = getattr(process, "_dsfst_children", [])
    if active:
        try:
            # Injectors start a new session, so this group contains only this fault.
            if os.getpgid(process.pid) != process.pid:
                raise RuntimeError("Stress process does not own its process group")
            children = psutil.Process(process.pid).children(recursive=True)
            process._dsfst_children = children
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, psutil.NoSuchProcess):
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, getattr(signal, "SIGKILL", 9))
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
    _, remaining = psutil.wait_procs(children, timeout=2)
    remaining = [child for child in remaining if _running(child)]
    for child in remaining:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    _, remaining = psutil.wait_procs(remaining, timeout=2)
    if any(_running(child) for child in remaining):
        raise RuntimeError("Stress workers have not stopped; retry the reset")
    return active or bool(children)
