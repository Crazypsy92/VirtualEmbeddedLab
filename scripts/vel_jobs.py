"""Foreground job control for WSL acceptances."""
from contextlib import contextmanager
import fcntl
import json
import os
import signal
import sys


class BusyWorkspace(Exception):
    pass


def lock_owner(stream):
    try:
        stream.seek(0)
        owner = json.load(stream)
        return owner if isinstance(owner, dict) else {}
    except (OSError, ValueError):
        return {}


def busy_message(path, owner):
    pid = owner.get("pid")
    detail = f"（PID {pid}）" if pid else ""
    return (f"已有验收任务占用该工作区{detail}。若刚按过 Ctrl+Z，请在原终端运行 "
            f"jobs -l，然后用 fg 恢复，或恢复后按 Ctrl+C 安全停止。锁文件：{path}")


@contextmanager
def workspace_lock(path):
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BusyWorkspace(busy_message(path, lock_owner(stream))) from None
        stream.seek(0)
        stream.truncate()
        json.dump({"pid": os.getpid(), "command": sys.argv}, stream)
        stream.flush()
        yield


def lock_status(path):
    if not path.exists():
        return False, {}
    with path.open() as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True, lock_owner(stream)
        return False, {}


def install_cancel_handlers():
    def cancel(signum, _frame):
        if signum == signal.SIGTSTP:
            print("Ctrl+Z：正在取消验收并释放锁。下次可用 Ctrl+C 停止。", file=sys.stderr, flush=True)
        raise SystemExit(130 if signum in (signal.SIGINT, signal.SIGTSTP) else 128 + signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGTSTP):
        signal.signal(signum, cancel)
