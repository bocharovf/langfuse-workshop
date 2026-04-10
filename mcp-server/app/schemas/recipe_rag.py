from pydantic import BaseModel

from schemas.common import Ingredient


class RecipeRagRequest(BaseModel):
    search_query: str


class Recipe(BaseModel):
    url: str
    name: str
    ingredients: list[Ingredient]


class RecipeRagResponse(BaseModel):
    recipes: list[Recipe]
