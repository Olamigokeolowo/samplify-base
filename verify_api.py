import requests
import json

BASE_URL = "http://localhost:8000"

def test_categories():
    print("\n--- Testing Categories ---")
    response = requests.get(f"{BASE_URL}/api/categories")
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))

def test_products():
    print("\n--- Testing Products ---")
    response = requests.get(f"{BASE_URL}/api/products")
    print(f"Status: {response.status_code}")
    # Just print the first one for brevity
    print(json.dumps(response.json()[0], indent=2))

def test_cart_add_variants():
    print("\n--- Testing Cart Add Variants ---")
    payload1 = {"product_id": 1, "quantity": 1, "color": "Red", "size": "L"}
    payload2 = {"product_id": 1, "quantity": 1, "color": "Blue", "size": "M"}
    
    requests.post(f"{BASE_URL}/api/cart/add", json=payload1)
    response = requests.post(f"{BASE_URL}/api/cart/add", json=payload2)
    
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json()["cart"], indent=2))

if __name__ == "__main__":
    try:
        test_categories()
        test_products()
        test_cart_add_variants()
    except Exception as e:
        print(f"Error: {e}")
