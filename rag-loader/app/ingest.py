import os
import csv
import json
import requests

from typing import List, Dict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# ==============================
# Config
# ==============================

LLM_URL = os.getenv("LLM_URL")
LLM_TOKEN = os.getenv("LLM_TOKEN")

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")

COLLECTION_NAME = "recipes"
DATA_PATH = "/data/recipes_short.csv"
MAX_EMBED_TEXT = 2000

# ==============================
# Clients
# ==============================

client = QdrantClient(url=QDRANT_URL)

# ==============================
# Embeddings
# ==============================

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


# ==============================
# Data loading
# ==============================

def load_recipes() -> List[Dict]:

    recipes = []

    with open(DATA_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for idx, row in enumerate(reader):

            ingredients = row["ingredients"]

            ingredients_list = []
            # normalize ingredients
            if isinstance(ingredients, str):
                ingredients_str = ingredients.replace("'", '"').replace("None", "null")
                ingredients_json = json.loads(ingredients_str)
                for k, v in ingredients_json.items():
                    ingredients_list.append({
                        "name": k,
                        "amount": v,
                    })

            recipes.append({
                "url": row["url"],
                "name": row["name"],
                "ingredients": ingredients_list
            })
    return recipes


# ==============================
# Vector building
# ==============================

def build_vectors(recipe_doc: Dict):

    recipe_text = recipe_doc["name"]
    ingredients_text_list = []
    for i in recipe_doc["ingredients"]:
        name = i["name"]
        amount = i["amount"]
        ingredients_text_list.append(f'{name}: {amount}' if amount else name)
    ingredients_text = "\n".join(ingredients_text_list)

    recipe_embedding = embed(recipe_text)
    ingredients_embedding = embed(ingredients_text)

    return {
        "url": recipe_doc["url"],
        "payload": recipe_doc,
        "vectors": {
            "recipe_vector": recipe_embedding,
            "ingredients_vector": ingredients_embedding
        }
    }


# ==============================
# Collection
# ==============================

def collection_exists():

    print("Checking recipes collection...")
    print("QDRANT_URL:", QDRANT_URL)

    exists = client.collection_exists(collection_name=COLLECTION_NAME)

    print(f"Collection '{COLLECTION_NAME}' exists:", exists)

    return exists

def create_collection(example_vector_size: int):

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "recipe_vector": VectorParams(
                size=example_vector_size,
                distance=Distance.COSINE,
            ),
            "ingredients_vector": VectorParams(
                size=example_vector_size,
                distance=Distance.COSINE,
            ),
        },
    )


# ==============================
# Ingest
# ==============================

def ingest():

    print("Loading recipes dataset...")
    recipes = load_recipes()

    if not recipes:
        raise RuntimeError("recipes.csv is empty")

    print("Creating embeddings for first item to determine vector size...")

    first_vectors = build_vectors(recipes[0])
    vector_size = len(first_vectors["vectors"]["recipe_vector"])

    print("Creating Qdrant collection...")
    create_collection(vector_size)

    points = []

    print("Building vectors...")

    for idx, recipe in enumerate(recipes):

        try:

            vectors = build_vectors(recipe)

            points.append(
                PointStruct(
                    id=idx,
                    vector=vectors["vectors"],
                    payload=vectors["payload"]
                )
            )

        except Exception as e:
            print(f"Failed to process recipe {idx}: {e}")

    print(f"Uploading {len(points)} recipes...")

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )

    print("Ingest completed.")


def collection_has_points():

    try:
        count = client.count(
            collection_name=COLLECTION_NAME,
            exact=True
        ).count

        return count > 0

    except:
        return False

# ==============================
# Auto run
# ==============================

def main():

    print("Checking recipes collection...")

    if collection_exists() and collection_has_points():
        print("Collection 'recipes' already exists. Skipping ingest.")
        return

    print("Collection not found. Starting ingest...")
    ingest()


if __name__ == "__main__":
    main()
