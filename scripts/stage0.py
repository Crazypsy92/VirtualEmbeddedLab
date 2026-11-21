#!/usr/bin/env python3
from vel_env import tool_environment
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
"""Read-only environment inventory and actual Stage 0 acceptance."""
import datetime
import os
import pathlib
import shutil
import subprocess
import sys
root = pathlib.Path(__file__).resolve().parents[1]
out = pathlib.Path(os.environ.get('VEL_STAGE0_EVIDENCE', str(root/'evidence/stage0')))
out.mkdir(parents=True, exist_ok=True)
failed = []
def run(name, command):
    try:
        r = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        text = r.stdout
        rc = r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        text, rc = str(e), 1
    (out / (name + '.log')).write_text('$ ' + ' '.join(command) + '\n' + text + '\nexit=' + str(rc) + '\n')
    print(name, 'PASS' if rc == 0 else 'FAIL', flush=True)
    if rc: failed.append(name)
    return text
run('environment', ['bash', '-lc', 'date -Is; cat /etc/os-release; uname -a; lscpu; free -h; df -h .; for t in gcc g++ arm-none-eabi-gcc arm-none-eabi-objcopy arm-none-eabi-objdump arm-none-eabi-readelf cmake ninja git qemu-system-arm gdb-multiarch python3; do command -v "$t" || exit 1; "$t" --version | head -n 1; done'])
boards = run('qemu_machines', ['qemu-system-arm', '-machine', 'help'])
if 'mps2-an385' not in boards: failed.append('mps2-an385 support')
run('arm_target', ['arm-none-eabi-gcc', '-mcpu=cortex-m3', '-mthumb', '-Q', '--help=target'])
for preset in ['host-debug', 'arm-debug']:
    run(preset + '_configure', ['cmake', '--preset', preset])
    run(preset + '_build', ['cmake', '--build', '--preset', preset, '--verbose'])
run('host_ctest', ['ctest', '--preset', 'host-debug', '--output-on-failure', '-R', '^host_smoke$'])
run('host_run', [str(root / 'build/host/host_smoke')])
run('arm_elf', ['arm-none-eabi-readelf', '-h', '-S', '-l', str(root / 'build/arm/cortex_m3_demo.elf')])
report = '# Stage 0 acceptance\n\nDate: ' + datetime.datetime.now().astimezone().isoformat() + '\n\n'
report += 'Project: `' + str(root) + '`. Existing STM32 folders were empty; no parent Git repository or AGENTS.md found. Initial WSL access needed sandbox escalation. Initial apt installation could not authenticate sudo; user completed installation in their own terminal.\n\n'
report += 'WSL distribution: Ubuntu, WSL2 (verified with Windows `wsl --list --verbose`). Detailed versions and resources: [environment](../evidence/stage0/environment.log).\n\n'
report += 'Host Build / Run / CTest, ARM Build, Cortex-M3 Thumb target, and QEMU board inventory: ' + ('PASS' if not failed else 'FAIL: ' + ', '.join(failed)) + '.\n\n'
report += 'Logs in `evidence/stage0/` contain exact commands, output and exit status. Stage 0 firmware is a build-only probe; functional startup is implemented only after this gate passes. No hardware operations performed.\n'
(out/'report.md' if os.environ.get('VEL_STAGE0_EVIDENCE') else root/'docs/stage0_report.md').write_text(report)
sys.exit(bool(failed))
