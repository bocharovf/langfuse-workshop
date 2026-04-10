from pydantic import BaseModel

from schemas.common import Ingredient


class RecipeCostRequest(BaseModel):
    ingredients: list[Ingredient]


class RecipeCostResponse(BaseModel):
    total_cost: float
