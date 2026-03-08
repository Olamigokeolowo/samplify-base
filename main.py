from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cart_store import carts, get_user_cart
from db import get_db_connection, init_auth_tables, init_payment_tables
from routes import auth, payments, products

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Connecting to database...")
    conn = get_db_connection()
    if conn:
        print("Connection successful!")
        conn.close()
        init_auth_tables()
        init_payment_tables()
        print("Payment tables ready.")
    else:
        print("Warning: Could not connect to database on startup.")
    yield

app = FastAPI(lifespan=lifespan)


# ========================
# CORS (allow React)
# ========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(auth.router)
app.include_router(payments.router)
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
    product_id: int
    quantity: int = 1
    color: str = "Default"
    size: str = "M"


class UpdateQuantityRequest(BaseModel):
    action: str  # "increase" or "decrease"


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

    from routes.products import MOCK_PRODUCTS
    product = next((p for p in MOCK_PRODUCTS if p["id"] == item.product_id), None)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check for existing item with same variants
    for cart_item in cart:
        if (cart_item["id"] == item.product_id and 
            cart_item["color"] == item.color and 
            cart_item["size"] == item.size):
            cart_item["quantity"] += item.quantity
            return {"message": "Quantity updated", "cart": cart}

    new_item = {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "quantity": item.quantity,
        "image": product["image"],
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

@app.get("/api/db-test")
def test_db_connection():
    """Endpoint to test the database connection and return server time."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"status": "success", "db_time": result[0]}
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")


# ========================
# Run server
# ========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
