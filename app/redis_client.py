import redis
import json
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")
CART_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days — abandoned carts auto-expire

r = redis.from_url(REDIS_URL, decode_responses=True)


def _cart_key(user_id: int) -> str:
    return f"cart:{user_id}"


def get_cart_items(user_id: int) -> list[dict]:
    raw = r.get(_cart_key(user_id))
    if not raw:
        return []
    return json.loads(raw)


def save_cart_items(user_id: int, items: list[dict]) -> None:
    key = _cart_key(user_id)
    r.set(key, json.dumps(items), ex=CART_TTL_SECONDS)


def clear_cart(user_id: int) -> None:
    r.delete(_cart_key(user_id))