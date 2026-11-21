#!/usr/bin/env python3
"""ROS service client shared by one-shot commands and the runtime tests."""
import argparse
import json
from pathlib import Path

import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import Parameter, ParameterValue
from rcl_interfaces.srv import SetParameters
from std_srvs.srv import Trigger


class ServiceClient:
    def __enter__(self):
        rclpy.init()
        self.node = Node("vel_command_client")
        self.clients = {}
        return self

    def __exit__(self, *args):
        self.node.destroy_node()
        rclpy.shutdown()

    def client(self, command):
        service_type = SetParameters if command == "set_rate" else Trigger
        if command not in self.clients:
            self.clients[command] = self.node.create_client(service_type, "/vel/" + command)
        return self.clients[command]

    def wait_for(self, commands):
        for command in commands:
            if not self.client(command).wait_for_service(timeout_sec=8):
                raise TimeoutError(f"ROS service is unavailable: {command}")

    def call(self, command, value=20):
        self.wait_for([command])
        if command == "set_rate":
            request = SetParameters.Request()
            request.parameters = [Parameter(
                name="period_ms", value=ParameterValue(type=2, integer_value=value))]
        else:
            request = Trigger.Request()
        future = self.client(command).call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=8)
        if not future.done() or future.result() is None:
            raise TimeoutError(f"ROS service did not answer: {command}")
        response = future.result()
        if command == "set_rate":
            return {"success": response.results[0].successful,
                    "message": response.results[0].reason}
        return {"success": response.success, "message": response.message}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--value", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with ServiceClient() as client:
        data = client.call(args.command, args.value)
    args.output.write_text(json.dumps(data) + chr(10))


if __name__ == "__main__":
    main()
