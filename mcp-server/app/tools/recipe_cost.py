import random

from schemas.recipe_cost import RecipeCostRequest
from tools.common import simulate_tool_timeout_if_needed


def calculate_total_cost(request: RecipeCostRequest) -> float:
    simulate_tool_timeout_if_needed()

    total = 0

    for _ in request.ingredients:
        total += random.uniform(0.5, 2.0)

    return round(total, 2)
