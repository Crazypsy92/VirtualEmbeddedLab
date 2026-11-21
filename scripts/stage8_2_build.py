"""Build the native RTU slave in the current project workspace."""
from vel_env import ROOT, native_build, work

if __name__ == "__main__":
    native_build(ROOT / "zephyr/apps/modbus_rtu_slave", work("modbus_stage8_2_ws") / "build")
