import httpx
import os
from dotenv import load_dotenv

load_dotenv()

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8003")


async def get_product(product_id: int) -> dict | None:
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            resp = await client.get(f"{PRODUCT_SERVICE_URL}/api/products/{product_id}")
            if resp.status_code == 200:
                return resp.json()
            return None
        except httpx.RequestError:
            # product-service unreachable — graceful fallback, not a crash
            return None