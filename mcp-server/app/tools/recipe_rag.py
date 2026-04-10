import os
import requests

from qdrant_client import QdrantClient

from schemas.recipe_rag import RecipeRagRequest, Recipe
from tools.common import simulate_tool_timeout_if_needed


QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
LLM_URL = os.getenv("LLM_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
LLM_TOKEN = os.getenv("LLM_TOKEN")

COLLECTION_NAME = "recipes"
MAX_EMBED_TEXT = 2000
TOP_K = 5

client = QdrantClient(url=QDRANT_URL)


def embed(text: str):
    if isinstance(text, list):
        text = ", ".join(text)

    text = str(text)
    if len(text) > MAX_EMBED_TEXT:
        text = text[:MAX_EMBED_TEXT]

    url = f"{LLM_URL}/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {LLM_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    return data["data"][0]["embedding"]


def search_recipes(request: RecipeRagRequest) -> list[Recipe]:
    simulate_tool_timeout_if_needed()

    query_vector = embed(request.search_query)

    # search by recipe name
    name_hits = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        using="recipe_vector",
        limit=TOP_K
    ).points

    # search by ingredients
    ingredient_hits = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        using="ingredients_vector",
        limit=TOP_K
    ).points

    results = {}

    # merge results
    for hit in name_hits + ingredient_hits:

        recipe_id = hit.id

        if recipe_id not in results:
            results[recipe_id] = {
                "score": hit.score,
                "payload": Recipe(**hit.payload),
            }
        else:
            results[recipe_id]["score"] = max(results[recipe_id]["score"], hit.score)

    # sort by score
    sorted_results = sorted(
        results.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    return [r["payload"] for r in sorted_results[:TOP_K]]
