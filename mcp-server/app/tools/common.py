from time import sleep

from failure_sim import should_request_timeout


def simulate_tool_timeout_if_needed():
    # чуть дольше таймаута клиента (5 с): синхронный sleep блокирует весь сервер,
    # поэтому долгая пауза ломала бы и повторные попытки
    if should_request_timeout():
        sleep(6)
