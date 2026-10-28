"""Thin wrapper over the OpenAI SDK: structured-output calls per role, and embeddings."""
import json
import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

from common.config import PROJECT_ROOT, load_config


@lru_cache(maxsize=1)
def client() -> OpenAI:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY (or OPEN_AI_API_KEY) in the environment or in .env")
    return OpenAI(api_key=api_key, max_retries=load_config()["llm"]["max_retries"])


def structured(role: str, input, schema: dict, schema_name: str, instructions: str | None = None) -> dict:
    """Call the model configured for `role` and return its output parsed against `schema` (strict)."""
    response = client().responses.create(
        model=load_config()["models"][role],
        instructions=instructions,
        input=input,
        text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
    )
    return json.loads(response.output_text)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the configured embedding model, in batches."""
    config = load_config()
    vectors = []
    batch = config["llm"]["embedding_batch_size"]
    for start in range(0, len(texts), batch):
        response = client().embeddings.create(
            model=config["models"]["embedding"],
            input=texts[start:start + batch],
            dimensions=config["models"]["embedding_dimensions"],
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors
