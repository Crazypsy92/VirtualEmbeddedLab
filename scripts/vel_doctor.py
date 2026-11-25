"""Read-only dependency checks for the Ubuntu installation profiles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys

from vel_env import ROOT, ZEPHYR_REV, tool_environment, work, zephyr_base


def capture(argv, env):
    try:
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "zephyr"), default="core")
    args = parser.parse_args(argv)
    env = tool_environment()
    distro = platform.freedesktop_os_release() if Path("/etc/os-release").exists() else {}
    print(f"Project: {ROOT}")
    print(f"Platform: {distro.get('PRETTY_NAME', platform.system())} / {platform.machine()} / "
          + ("WSL" if "microsoft" in platform.release().lower() else platform.release()))
    print(f"Install profile: {args.profile}; UID {os.getuid()}; interpreter {sys.executable}")
    if distro.get("ID") != "ubuntu" or distro.get("VERSION_ID") != "24.04" or platform.machine() != "x86_64":
        print("  NOTE: dependencies and clean CI cover Ubuntu 24.04 x86_64.")
    required_ok = True

    def check(name, value, expected, fix, required=True):
        nonlocal required_ok
        state = "OK" if value else "MISSING/INCOMPATIBLE" if required else "OPTIONAL"
        print(f"[{state}] {name} — {value or 'unavailable'} (expected {expected})")
        if not value:
            print(f"    {fix}")
            required_ok &= not required

    apt = f"bash scripts/bootstrap_ubuntu.sh --profile {args.profile} --install-system-deps"
    init = f"bash scripts/bootstrap_ubuntu.sh --profile {args.profile} --init"
    check("Permissions", "normal user, project writable" if os.getuid() and os.access(ROOT, os.W_OK) else "",
          "a non-root developer with a writable checkout", "Open the checkout as your normal Ubuntu user.")
    check("Python", platform.python_version() if sys.version_info[:2] == (3, 12) else "",
          f"3.12 (found {platform.python_version()})", "Use /usr/bin/python3 on Ubuntu 24.04.")
    for name, minimum in (("git", None), ("gcc", None), ("g++", None), ("cmake", (3, 22)),
                          ("ctest", (3, 22)), ("ninja", None), ("arm-none-eabi-gcc", None),
                          ("arm-none-eabi-objcopy", None), ("qemu-system-arm", None), ("gdb-multiarch", None)):
        path = shutil.which(name, path=env["PATH"])
        raw = capture([path, "--version"], env) if path else ""
        version = raw.splitlines()[0] if raw else ""
        match = re.search(r"(\d+)\.(\d+)", version)
        compatible = minimum is None or (match and tuple(map(int, match.groups())) >= minimum)
        check(name, version if compatible else "",
              (".".join(map(str, minimum)) + " or newer") if minimum else "Ubuntu 24.04 package", apt)
    machines = capture(["qemu-system-arm", "-machine", "help"], env)
    check("QEMU board", "mps2-an385" if "mps2-an385" in machines else "", "mps2-an385", apt)
    check("venv", capture(["/usr/bin/python3", "-c", "import ensurepip; print(ensurepip.version())"], env),
          "system python3-venv", apt)
    check("Tkinter", capture([sys.executable, "-c", "import tkinter; print(tkinter.TkVersion)"], env),
          "Tk 8.6", apt)
    check("GUI display", capture([sys.executable, "-c",
           "import tkinter as t; r=t.Tk(); r.withdraw(); print(r.tk.call('tk', 'windowingsystem')); r.destroy()"], env),
          "WSLg/X11 or Xvfb", "Use WSLg/desktop, or install xvfb and xauth for CI-style execution.", False)

    versions = capture([sys.executable, "-c",
        "import importlib.metadata as m; print(m.version('pymodbus'), m.version('pyserial'))"], env)
    check("Modbus Python", versions if versions == "3.11.4 3.5" else "", "pymodbus 3.11.4 / pyserial 3.5",
          init, args.profile == "zephyr")

    stage8 = args.profile == "zephyr"
    base = zephyr_base()
    version_path = base / "VERSION"
    version = dict(re.findall(r"^(VERSION_MAJOR|VERSION_MINOR|PATCHLEVEL)\s*=\s*(\d+)",
                              version_path.read_text(), re.MULTILINE)) if version_path.is_file() else {}
    revision = capture(["git", "-C", str(base), "rev-parse", "--show-toplevel"], env) if version else ""
    if revision == str(base):
        verified = capture(["git", "-C", str(base), "rev-parse", "HEAD"], env) == ZEPHYR_REV
    else:
        entry = json.loads((ROOT / "zephyr/versions.json").read_text())["sources"]["zephyr"]
        archive = base.parent / entry["archive"]
        verified = False
        if version and archive.is_file():
            with archive.open("rb") as stream:
                verified = hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"]
    zephyr_version = ".".join(version.get(key, "?") for key in ("VERSION_MAJOR", "VERSION_MINOR", "PATCHLEVEL"))
    check("Zephyr", f"{zephyr_version} ({base})" if verified and zephyr_version == "4.4.2" else "",
          f"4.4.2 / {ZEPHYR_REV[:12]}", "Run bootstrap with --profile zephyr --init.", stage8)
    zephyr_init = "bash scripts/bootstrap_ubuntu.sh --profile zephyr --init"
    west = capture([sys.executable, "-m", "west", "--version"], env)
    check("west", west if re.search(r"\bv?1\.5\.0\b", west) else "", "1.5.0", zephyr_init, stage8)
    check("DTC", capture(["dtc", "--version"], env), "Ubuntu device-tree-compiler", apt, stage8)
    check("Zephyr Python imports", capture([sys.executable, "-c",
          "import yaml, pykwalify, elftools, jsonschema; print('yaml, pykwalify, elftools, jsonschema')"], env),
          "pinned Zephyr profile", zephyr_init, stage8)

    override = env.get("VEL_ROS_SETUP")
    for distro, feature in (("jazzy", "Stage 5"), ("lyrical", "historical Stage 6/7")):
        setup = Path(override).expanduser() if override else Path(f"/opt/ros/{distro}/setup.bash")
        status = capture(["bash", "-c", 'source "$1" && test "$ROS_DISTRO" = "$2" && '
                          '/usr/bin/python3 -c "import rclpy" && printf "%s" "$ROS_DISTRO"',
                          "doctor-ros", str(setup), distro], env) if setup.is_file() else ""
        check(f"ROS 2 {distro}", f"{status} / rclpy import ({setup})" if status else "", feature,
              f"See docs/installation.md. Configure a matching official ROS installation for {feature}.", False)

    renode = capture(["renode", "--version"], env)
    cache = work("simulation_stage8_1_ws") / "renode-1.17.0.tar.gz"
    archive_version = ""

    if cache.is_file():
        lock = json.loads((ROOT / "simulation/renode/package.lock.json").read_text())
        with cache.open("rb") as stream:
            valid = hashlib.file_digest(stream, "sha256").hexdigest() == lock["sha256"]
        if valid:
            archive_version = f"1.17.0 archive verified ({cache})"
    print(f"[INFO] Renode on PATH: {renode.splitlines()[0] if renode else 'unavailable'}")
    check("Renode archive", archive_version,
          "verified 1.17.0 portable archive", "See docs/stage_history.md for the independent Renode setup.", False)
    historical = [p for p in ("micro_ros/dependencies.lock.json", "micro_ros/arm/colcon.meta",
                             "micro_ros/stage7_arm.meta") if not (ROOT / p).is_file()]
    if historical:
        print("[BLOCKED] Historical Stage 6/7 inputs: " + ", ".join(historical))
    print(f"{args.profile}: {'READY' if required_ok else 'NOT READY'}")
    return int(not required_ok)
