from time import sleep

from failure_sim import should_request_timeout


def simulate_tool_timeout_if_needed():
    if should_request_timeout():
        sleep(10)
