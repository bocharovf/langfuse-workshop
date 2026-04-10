from typing import Optional

from pydantic import BaseModel


class Ingredient(BaseModel):
    name: str
    amount: Optional[str]
