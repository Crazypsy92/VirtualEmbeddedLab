#!/usr/bin/env python3
"""Bounded, owned QEMU process: validate real UART output plus exit status."""
import argparse
import os
import pathlib
import re
import signal
import subprocess
import sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
def command(elf, machine='mps2-an385'):
    return ['qemu-system-arm', '-M', machine, '-cpu', 'cortex-m3', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-semihosting-config', 'enable=on,target=native', '-kernel', str(elf)]
def validate(text):
    required = ['[BOOT] Cortex-M3 Starting', '[INIT] Data/BSS OK', '[UART] PASS', '[SVC] count=2 msp=1 psp=1', '[PENDSV] count=1 pending=1', '[EXCEPTION] failures=0', '[MAIN] PASS']
    if any(s not in text for s in required) or '[FAULT]' in text or 'FAIL' in text:
        raise ValueError('UART functional evidence missing or failure reported')
    first = re.search(r'\[TICK\] first=(\d+)', text)
    final = re.search(r'\[TICK\] final=(\d+)', text)
    if not first or not final or not (0 < int(first[1]) < int(final[1])):
        raise ValueError('SysTick did not increase')
def terminate(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--elf', type=pathlib.Path, default=ROOT / 'build/arm/cortex_m3_demo.elf')
    ap.add_argument('--timeout', type=float, default=10)
    ap.add_argument('--machine', default='mps2-an385')
    ap.add_argument('--halt', action='store_true', help='Exercise genuine QEMU timeout with CPU halted')
    ap.add_argument('--discard-uart', action='store_true', help='Exercise evidence rejection')
    args = ap.parse_args()
    cmd = command(args.elf, args.machine)
    if args.halt: cmd += ['-S']
    if args.discard_uart: cmd[cmd.index('stdio')] = 'null'
    print('$ ' + ' '.join(cmd), flush=True)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    except OSError as e:
        print(e); return 2
    print('QEMU_PID=' + str(proc.pid), flush=True)
    rc = 1
    try:
        try: output, _ = proc.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            terminate(proc)
            output, _ = proc.communicate(timeout=2)
            print(output, end='')
            print('TIMEOUT: process group terminated and reaped')
            return 124
        print(output, end='')
        print('QEMU_EXIT=' + str(proc.returncode))
        if proc.returncode != 0: return 2
        validate(output)
        rc = 0
    except ValueError as e:
        print('VALIDATION ERROR:', e)
    finally:
        terminate(proc)
    return rc
if __name__ == '__main__':
    from vel_jobs import install_cancel_handlers
    install_cancel_handlers()
    sys.exit(main())
