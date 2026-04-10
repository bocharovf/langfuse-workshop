from observability import langfuse


MODEL_DEFINITIONS = [
    ("llama-3.3-70b-instruct", 0.1),
    ("llama-3.1-8b-instruct", 0.001),
]


def create_model_definitions():
    full_model_list = []
    current_page = 1
    fetch_finished = False
    while not fetch_finished:
        models_response = langfuse.api.models.list(page=current_page, limit=100)
        full_model_list.extend(models_response.data)
        fetch_finished = current_page == models_response.meta.total_pages
        current_page += 1

    model_resolver = {m.model_name: m for m in full_model_list}
    for model_defn in MODEL_DEFINITIONS:
        model_name, input_price = model_defn
        if model_name in model_resolver:
            print("Found existing model definition: " + model_name)
            continue

        langfuse.api.models.create(
            model_name=model_name,
            match_pattern=f"(?i)^({model_name})$",
            unit="TOKENS",
            input_price=input_price,
            output_price=input_price * 2,
        )
        print("Created new model definition: " + model_name)


if __name__ == "__main__":
    print("Creating model definitions...")
    create_model_definitions()
