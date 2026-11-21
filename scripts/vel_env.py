"""Resolve project dependencies without binding the checkout to one WSL account."""
from pathlib import Path
import os
import pwd
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ZEPHYR_REV = "dccb09599635bdff17633fa7e9dab014b91dce90"


def work(name):
    return Path(os.environ.get("VEL_WORK_ROOT", ROOT / "build/workspaces")).expanduser().resolve() / name


def nonroot():
    account = pwd.getpwuid(os.getuid())
    if os.getuid() == 0 or Path.home() != Path(account.pw_dir):
        raise SystemExit("Run from a normal WSL login with the matching HOME.")


def zephyr_base():
    explicit = os.environ.get("VEL_ZEPHYR_BASE") or os.environ.get("ZEPHYR_BASE")
    pinned = ROOT / "build/recovery-zephyr" / ("zephyr-" + ZEPHYR_REV)
    return Path(explicit).expanduser().resolve() if explicit else pinned


def tool_environment():
    env = os.environ.copy()
    local = Path(env.get("VEL_TOOLS_ROOT", ROOT / "build/recovery-tools/root"))
    for key, locations in {
        "PATH": [local / "usr/bin"],
        "LD_LIBRARY_PATH": [local / "usr/lib/x86_64-linux-gnu"],
        "PYTHONPATH": [Path(env.get("VEL_PYTHON_PACKAGES", ROOT / "build/recovery-zephyr/python"))],
    }.items():
        paths = [str(p) for p in locations if p.is_dir()]
        if paths:
            env[key] = os.pathsep.join(dict.fromkeys(paths + env.get(key, "").split(os.pathsep))).strip(os.pathsep)
    return env


def tool(name):
    return shutil.which(name, path=tool_environment()["PATH"]) or name


def zephyr_environment(variant="host"):
    env = tool_environment()
    env.update(ZEPHYR_BASE=str(zephyr_base()), ZEPHYR_TOOLCHAIN_VARIANT=variant)
    if variant == "cross-compile":
        env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "4")
        env["CROSS_COMPILE"] = tool("arm-none-eabi-gcc").removesuffix("gcc")
        modules = [zephyr_base().parent / "modules/hal" / name for name in ("cmsis", "cmsis_6")]
        if all((path / "zephyr/module.yml").is_file() for path in modules):
            env.setdefault("ZEPHYR_MODULES", ";".join(map(str, modules)))
    return env


def native_build(app, output, options=(), log=None):
    zephyr = zephyr_base()
    if not (zephyr / "VERSION").is_file():
        raise SystemExit(f"Zephyr not found at {zephyr}. Set VEL_ZEPHYR_BASE.")
    env = zephyr_environment()
    commands = [
        ["cmake", "-S", app, "-B", output, "-G", "Ninja", "-DBOARD=native_sim/native/64",
         "-DBUILD_VERSION=" + ZEPHYR_REV[:12], "-DDTC=" + tool("dtc"), *options],
        ["cmake", "--build", output, "--parallel", "4"],
    ]
    for command in commands:
        if log is not None:
            print(shlex.join(map(str, command)), file=log, flush=True)
        subprocess.run(command, cwd=zephyr, env=env, check=True, timeout=180,
                       stdout=log, stderr=subprocess.STDOUT if log is not None else None)


def ros_setup():
    active = os.environ.get("VEL_ROS_SETUP")
    if active:
        setup = Path(active).expanduser()
    else:
        dist = os.environ.get("ROS_DISTRO")
        preferred = Path("/opt/ros") / dist / "setup.bash" if dist else None
        installed = sorted(Path("/opt/ros").glob("*/setup.bash"))
        setup = preferred if preferred and preferred.is_file() else (
            installed[0] if len(installed) == 1 else None)
    if setup is None or not setup.is_file():
        raise SystemExit("Set VEL_ROS_SETUP to the installed ROS 2 setup.bash.")
    return setup


def ros_environment():
    nonroot()
    result = subprocess.run(
        ["bash", "-c", 'set -e; source "$1" >&2; env -0', "vel-ros", ros_setup()],
        env=tool_environment(), capture_output=True, text=True, check=True, timeout=15,
    )
    return dict(item.split("=", 1) for item in result.stdout.split("\0") if item)
