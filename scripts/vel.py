#!/usr/bin/env python3
"""Local entry point for the portable build and test commands."""
import argparse
import os
import subprocess
import sys

from vel_env import ROOT, nonroot, tool, tool_environment, zephyr_base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["doctor", "host", "sanitize", "arm", "freertos",
                                          "zephyr", "ros", "gateway", "reliability", "dashboard"])
    args, forwarded = parser.parse_known_args()
    nonroot()
    env = tool_environment()
    presets = {"host": "host-debug", "sanitize": "host-sanitize",
               "arm": "arm-debug", "freertos": "freertos-debug"}
    scripts = {"zephyr": "accept_stage4.py", "ros": "setup_stage5.py",
               "gateway": "accept_stage8_3.py", "reliability": "accept_stage8_3_1.py",
               "dashboard": "vel_dashboard.py"}
    if args.target == "doctor":
        print("Project:", ROOT)
        print("Zephyr:", zephyr_base())
        for name in ("cmake", "ninja", "gcc", "arm-none-eabi-gcc", "dtc", "qemu-system-arm",
                     "gdb-multiarch", "colcon"):
            path = tool(name)
            print(f"{name}: {path if path != name else 'not found'}")
        return 0
    if args.target in presets:
        if forwarded:
            parser.error("This target does not accept additional arguments.")
        preset = presets[args.target]
        env.setdefault("VEL_STAGE1_EVIDENCE", str(ROOT / "build/evidence/arm"))
        env.setdefault("VEL_STAGE3_EVIDENCE", str(ROOT / "build/evidence/freertos"))
        for command in (["cmake", "--preset", preset],
                        ["cmake", "--build", "--preset", preset, "--parallel", "4"],
                        ["ctest", "--preset", preset]):
            result = subprocess.run(command, cwd=ROOT, env=env, timeout=240)
            if result.returncode:
                return result.returncode
        return 0
    if args.target == "zephyr":
        env.setdefault("VEL_STAGE4_EVIDENCE", str(ROOT / "build/evidence/zephyr"))
    os.chdir(ROOT)
    script = ROOT / "scripts" / scripts[args.target]
    os.execve(sys.executable, [sys.executable, str(script), *forwarded], env)


if __name__ == "__main__":
    sys.exit(main())
