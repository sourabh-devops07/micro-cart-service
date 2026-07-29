from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import redis_client, product_client, schemas
from .auth import get_current_user_id

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="cart-service")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: HTTPException(status_code=429, detail="Too many requests"))
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/cart/items")
@limiter.limit("20/minute")
async def add_item(
    request: Request,
    input: schemas.AddItemInput,
    user_id: int = Depends(get_current_user_id),
):
    # Stock check — talk to product-service before adding
    product = await product_client.get_product(input.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.get("stock_quantity", 0) < input.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock available")

    items = redis_client.get_cart_items(user_id)

    existing = next((i for i in items if i["product_id"] == input.product_id), None)
    if existing:
        existing["quantity"] += input.quantity
    else:
        items.append({"product_id": input.product_id, "quantity": input.quantity})

    redis_client.save_cart_items(user_id, items)
    return await _build_cart_response(items)


@app.get("/api/cart")
async def view_cart(user_id: int = Depends(get_current_user_id)):
    items = redis_client.get_cart_items(user_id)
    return await _build_cart_response(items)


@app.patch("/api/cart/items/{product_id}")
async def update_quantity(
    product_id: int,
    input: schemas.UpdateQuantityInput,
    user_id: int = Depends(get_current_user_id),
):
    if input.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive; use DELETE to remove item")

    items = redis_client.get_cart_items(user_id)
    item = next((i for i in items if i["product_id"] == product_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not in cart")

    item["quantity"] = input.quantity
    redis_client.save_cart_items(user_id, items)
    return await _build_cart_response(items)


@app.delete("/api/cart/items/{product_id}")
async def remove_item(product_id: int, user_id: int = Depends(get_current_user_id)):
    items = redis_client.get_cart_items(user_id)
    new_items = [i for i in items if i["product_id"] != product_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Item not in cart")

    redis_client.save_cart_items(user_id, new_items)
    return await _build_cart_response(new_items)


@app.delete("/api/cart")
async def clear_cart(user_id: int = Depends(get_current_user_id)):
    redis_client.clear_cart(user_id)
    return {"message": "Cart cleared"}


async def _build_cart_response(items: list[dict]) -> dict:
    """API composition: cart only stores product_id + quantity — enrich with
    live name/price/image from product-service. If product-service is
    unreachable, fall back gracefully instead of failing the whole cart."""
    enriched = []
    total = 0.0

    for item in items:
        product = await product_client.get_product(item["product_id"])
        if product:
            line_total = product["price"] * item["quantity"]
            total += line_total
            enriched.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "name": product["name"],
                "price": product["price"],
                "image_url": product.get("image_url"),
                "line_total": round(line_total, 2),
            })
        else:
            enriched.append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "name": None,
                "price": None,
                "image_url": None,
                "line_total": None,
                "note": "Product details unavailable right now",
            })

    return {"items": enriched, "total": round(total, 2)}