"""Build the native Modbus gateway in the current project workspace."""
import json
import os
from vel_env import ROOT, native_build, work

if __name__ == "__main__":
    workspace = work("gateway_stage8_3_ws")
    port = int(os.environ.get("VEL_GATEWAY_PORT", "15020"))
    native_build(ROOT / "zephyr/apps/modbus_tcp_gateway", workspace / "build",
                 ["-DGW_PORT=" + str(port)])
    (workspace / "port.json").write_text(json.dumps({"port": port}) + chr(10))
