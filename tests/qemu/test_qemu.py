import os
import pathlib
import re
import subprocess
import sys
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
class QemuAcceptance(unittest.TestCase):
    def invoke(self, name, *args, expected=0):
        cmd = [sys.executable, str(ROOT/'scripts/run_qemu.py'), *args]
        r = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        out = pathlib.Path(os.environ.get('VEL_STAGE1_EVIDENCE', str(ROOT/'evidence/stage1')))/f'{name}.log'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('$ ' + ' '.join(cmd) + '\n' + r.stdout + '\nRUNNER_EXIT=' + str(r.returncode) + '\n')
        self.assertEqual(r.returncode, expected, r.stdout)
        pid = re.search(r'QEMU_PID=(\d+)', r.stdout)
        self.assertIsNotNone(pid)
        with self.assertRaises(ProcessLookupError): os.kill(int(pid[1]), 0)
        return r.stdout
    def test_boot_uart_ticks_exceptions(self):
        self.invoke('qemu_functional')
    def test_timeout_cleanup(self):
        self.assertIn('TIMEOUT', self.invoke('qemu_timeout', '--halt', '--timeout', '0.4', expected=124))
    def test_abnormal_exit(self):
        self.assertIn('QEMU_EXIT=1', self.invoke('qemu_abnormal', '--machine', 'vel-invalid-board', expected=2))
    def test_missing_evidence_rejected(self):
        self.assertIn('VALIDATION ERROR', self.invoke('qemu_missing_uart', '--discard-uart', expected=1))
if __name__ == '__main__': unittest.main(verbosity=2)
