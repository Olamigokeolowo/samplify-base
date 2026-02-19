from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

app = FastAPI()

# ========================
# CORS (allow React)
# ========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# Models
# ========================
class CartItem(BaseModel):
    id: int
    name: str
    price: float
    quantity: int
    image: str
    color: str
    size: str


class AddToCartRequest(BaseModel):
    id: int
    name: str
    price: float
    image: str
    color: str
    size: str


class UpdateQuantityRequest(BaseModel):
    action: str  # "increase" or "decrease"


# ========================
# In-memory storage
# ========================
carts = {}

def get_user_cart(user_id: str = "default_user"):
    if user_id not in carts:
        carts[user_id] = []
    return carts[user_id]


# ========================
# Routes
# ========================

@app.get("/")
def root():
    return {"message": "FastAPI Cart Backend is running"}


@app.get("/api/cart", response_model=List[CartItem])
def get_cart(user_id: str = "default_user"):
    return get_user_cart(user_id)


@app.post("/api/cart/add")
def add_to_cart(item: AddToCartRequest, user_id: str = "default_user"):
    cart = get_user_cart(user_id)

    for cart_item in cart:
        if cart_item["id"] == item.id:
            cart_item["quantity"] += 1
            return {"message": "Quantity increased", "cart": cart}

    new_item = {
        "id": item.id,
        "name": item.name,
        "price": item.price,
        "quantity": 1,
        "image": item.image,
        "color": item.color,
        "size": item.size,
    }

    cart.append(new_item)
    return {"message": "Item added to cart", "cart": cart}


@app.put("/api/cart/{item_id}/quantity")
def update_quantity(item_id: int, request: UpdateQuantityRequest, user_id: str = "default_user"):
    cart = get_user_cart(user_id)

    for item in cart:
        if item["id"] == item_id:
            if request.action == "increase":
                item["quantity"] += 1
            elif request.action == "decrease":
                if item["quantity"] <= 1:
                    raise HTTPException(status_code=400, detail="Quantity cannot be less than 1")
                item["quantity"] -= 1
            else:
                raise HTTPException(status_code=400, detail="Invalid action")

            return {"message": "Quantity updated", "cart": cart}

    raise HTTPException(status_code=404, detail="Item not found")


@app.delete("/api/cart/{item_id}")
def remove_item(item_id: int, user_id: str = "default_user"):
    cart = get_user_cart(user_id)

    new_cart = [item for item in cart if item["id"] != item_id]

    if len(new_cart) == len(cart):
        raise HTTPException(status_code=404, detail="Item not found")

    carts[user_id] = new_cart
    return {"message": "Item removed", "cart": new_cart}


@app.delete("/api/cart")
def clear_cart(user_id: str = "default_user"):
    carts[user_id] = []
    return {"message": "Cart cleared", "cart": []}


@app.get("/api/cart/summary")
def cart_summary(user_id: str = "default_user"):
    cart = get_user_cart(user_id)

    subtotal = sum(item["price"] * item["quantity"] for item in cart)
    tax = subtotal * 0.1
    total = subtotal + tax
    item_count = sum(item["quantity"] for item in cart)

    return {
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "total": round(total, 2),
        "item_count": item_count,
        "items": len(cart),
    }


# ========================
# Run server
# ========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
