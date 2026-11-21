"""Check the pinned Modbus packages in the selected local Python environment."""
import importlib.metadata
import os
import subprocess
import sys

from vel_env import nonroot, tool_environment, work

nonroot()
(work("modbus_stage8_2_ws") / "runs").mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, "-c",
                "import importlib.metadata as m; "
                "assert m.version('pymodbus') == '3.11.4'; "
                "assert m.version('pyserial') == '3.5'; "
                "print('Modbus host dependencies ready')"],
               env=tool_environment(), check=True, timeout=15)
