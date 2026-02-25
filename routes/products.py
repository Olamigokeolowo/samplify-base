from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(tags=["products"])

# Category Data for Homepage
MOCK_CATEGORIES = [
    {
        "id": 1,
        "name": "Apparel",
        "image": "https://images.unsplash.com/photo-1441984908796-9009773a4417?w=600&h=800&fit=crop",
        "link": "/shop?category=Apparel"
    },
    {
        "id": 2,
        "name": "Footwear",
        "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&h=800&fit=crop",
        "link": "/shop?category=Footwear"
    },
    {
        "id": 3,
        "name": "Accessories",
        "image": "https://images.unsplash.com/photo-1547949003-9792a18a2601?w=600&h=800&fit=crop",
        "link": "/shop?category=Accessories"
    }
]

class Category(BaseModel):
    id: int
    name: str
    image: str
    link: str

class Product(BaseModel):
    id: int
    name: str
    price: float
    original_price: Optional[float] = None
    description: str
    image: str
    category: str
    rating: float
    reviews: int
    stock: int
    featured: bool = False
    bestseller: bool = False

# Mock Data
MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "Classic White Tee",
        "price": 29.99,
        "original_price": 39.99,
        "description": "Essential everyday comfort in premium cotton.",
        "image": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?q=80&w=1000&auto=format&fit=crop",
        "category": "Apparel",
        "rating": 4.8,
        "reviews": 124,
        "stock": 50,
        "featured": True,
        "bestseller": True
    },
    {
        "id": 2,
        "name": "Raw Denim Jeans",
        "price": 89.00,
        "description": "Durable, high-quality denim that ages beautifully.",
        "image": "https://images.unsplash.com/photo-1542272604-787c3835535d?q=80&w=1000&auto=format&fit=crop",
        "category": "Apparel",
        "rating": 4.6,
        "reviews": 89,
        "stock": 30,
        "featured": False,
        "bestseller": True
    },
    {
        "id": 3,
        "name": "Leather Chelsea Boots",
        "price": 145.00,
        "description": "Elegant and versatile boots for any occasion.",
        "image": "https://images.unsplash.com/photo-1638247025967-b4e38f787b76?q=80&w=1000&auto=format&fit=crop",
        "category": "Footwear",
        "rating": 4.9,
        "reviews": 56,
        "stock": 15,
        "featured": True,
        "bestseller": False
    },
    {
        "id": 4,
        "name": "Canvas Backpack",
        "price": 45.00,
        "original_price": 55.00,
        "description": "Rugged canvas with leather accents for daily commute.",
        "image": "https://images.unsplash.com/photo-1547949003-9792a18a2601?q=80&w=1000&auto=format&fit=crop",
        "category": "Accessories",
        "rating": 4.7,
        "reviews": 210,
        "stock": 42,
        "featured": False,
        "bestseller": False
    }
]

@router.get("/api/products", response_model=List[Product])
async def get_products(
    category: Optional[str] = None,
    featured: Optional[bool] = None,
    bestseller: Optional[bool] = None,
    limit: Optional[int] = None
):
    result = MOCK_PRODUCTS
    if category:
        result = [p for p in result if p["category"] == category]
    if featured is not None:
        result = [p for p in result if p["featured"] == featured]
    if bestseller is not None:
        result = [p for p in result if p["bestseller"] == bestseller]
    if limit:
        result = result[:limit]
    return result

@router.get("/api/categories", response_model=List[Category])
async def get_categories():
    return MOCK_CATEGORIES

@router.get("/api/products/{product_id}", response_model=Product)
async def get_product(product_id: int):
    product = next((p for p in MOCK_PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
