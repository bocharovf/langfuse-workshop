import os
import random

from starlette_context import context as asgi_context

REQUEST_FAILURE_CHANCE_CONTEXT_KEY = "failure_chance"


def is_faulty_mode_on():
    return os.getenv("STEP_3", "False") == "True"


def init_request_failure_chance():
    asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] = random.random()


def should_request_fail():
    if not is_faulty_mode_on():
        return False

    return asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] < 0.25


def should_request_timeout():
    if not is_faulty_mode_on():
        return False

    return asgi_context[REQUEST_FAILURE_CHANCE_CONTEXT_KEY] > 0.75
