from typing import Any

# In-memory cart storage keyed by user id.
carts: dict[str, list[dict[str, Any]]] = {}


def get_user_cart(user_id: str = "default_user") -> list[dict[str, Any]]:
    if user_id not in carts:
        carts[user_id] = []
    return carts[user_id]
