import os
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(".env.local")


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a shared Supabase client configured from the environment."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)
