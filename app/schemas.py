from pydantic import BaseModel


class AddItemInput(BaseModel):
    product_id: int
    quantity: int = 1


class UpdateQuantityInput(BaseModel):
    quantity: int