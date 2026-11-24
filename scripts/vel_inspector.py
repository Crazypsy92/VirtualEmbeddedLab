"""Build and run the dedicated live dashboard firmware on MPS2 AN385."""
import os
import re
import subprocess
import sys

from run_qemu import command
from vel_env import ROOT, tool_environment

FIELDS = re.compile(r" ([a-z0-9_]+)=(\d+)")


def snapshot(log):
    """Return the most recent complete snapshot and its task table."""
    # The file can be tailed midway through a record, including its last line.
    frames = list(re.finditer(r"^VEL_BEGIN([^\n]*)\n((?:VEL_TASK [^\n]*\n)+)VEL_END\n",
                             log, flags=re.MULTILINE))
    for frame in reversed(frames):
        values = {k: int(v) for k, v in FIELDS.findall(frame[1])}
        tasks = []
        for row in frame[2].splitlines():
            _, name, rest = row.split(" ", 2)
            fields = {k: int(v) for k, v in FIELDS.findall(" " + rest)}
            if not {"id", "state", "priority", "stack_words"} <= fields.keys():
                break
            tasks.append((name, fields))
        else:
            if len(tasks) == values.get("tasks") and "tick" in values:
                return values, tasks
    return {}, []


def main():
    env = tool_environment()
    build = ROOT / "build/dashboard-inspector"
    subprocess.run(["cmake", "-S", ROOT, "-B", build, "-G", "Ninja",
                    "-DCMAKE_TOOLCHAIN_FILE=" + str(ROOT / "cmake/arm-none-eabi.cmake"),
                    "-DCMAKE_BUILD_TYPE=Debug", "-DVEL_FREERTOS=ON"],
                   env=env, check=True, timeout=180)
    subprocess.run(["cmake", "--build", build, "--target", "rtos_inspector", "--parallel", "4"],
                   env=env, check=True, timeout=180)
    args = command(build / "rtos_inspector.elf") + ["-nic", "none"]
    os.execvpe(args[0], args, env)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
