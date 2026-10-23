"""Shared helpers: read .env, connect to Neo4j and OpenAI with friendly errors."""
import os
import sys

from import_wiki import read_env, HERE

EMBED_MODEL = "text-embedding-3-small"   # 1536 numbers per text, matches the vector index
DEFAULT_CHAT_MODEL = "gpt-6-luna"        # override with OPENAI_CHAT_MODEL in .env


def load_env():
    env = read_env(os.path.join(HERE, ".env"))
    if not env:
        sys.exit("No .env file found next to the scripts.")
    return env


def connect_neo4j(env):
    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ImportError:
        sys.exit("Run: pip install -r requirements.txt   (inside the activated .venv)")
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USERNAME"], env["NEO4J_PASSWORD"]))
    try:
        driver.verify_connectivity()
    except AuthError:
        sys.exit("Neo4j login failed: check NEO4J_USERNAME / NEO4J_PASSWORD in .env")
    except ServiceUnavailable:
        sys.exit("Cannot reach Neo4j. Is the Aura instance Running (not Paused)?")
    return driver, env.get("NEO4J_DATABASE") or "neo4j"


def openai_client(env):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("Run: pip install -r requirements.txt   (inside the activated .venv)")
    key = env.get("OPENAI_API_KEY")
    if not key or key.startswith("sk-paste"):
        sys.exit("Add your key to .env as a line:  OPENAI_API_KEY=sk-...")
    return OpenAI(api_key=key)


def embed(client, texts):
    """Turn a list of texts into a list of vectors (lists of 1536 floats)."""
    import openai
    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    except openai.AuthenticationError:
        sys.exit("OpenAI rejected the API key. Check OPENAI_API_KEY in .env")
    except openai.RateLimitError as e:
        sys.exit("OpenAI rate limit or no credit on the account (check Billing):\n%s" % e)
    return [d.embedding for d in resp.data]
