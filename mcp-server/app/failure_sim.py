import os
import random

from starlette_context import context as asgi_context

REQUEST_FAILURE_CHANCE_CONTEXT_KEY = "failure_chance"

# доля запросов, которые завершаются ошибкой 500, и доля вызовов инструментов, которые зависают
FAILURE_RATE = 0.15
TIMEOUT_RATE = 0.15


def is_faulty_mode_on():
    return os.getenv("STEP_3", "False") == "True"


def init_request_failure_chance():
    asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] = random.random()


def should_request_fail():
    if not is_faulty_mode_on():
        return False

    return asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] < FAILURE_RATE


def should_request_timeout():
    if not is_faulty_mode_on():
        return False

    return asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] > 1 - TIMEOUT_RATE
