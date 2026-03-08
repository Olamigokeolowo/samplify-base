# Paystack Payment API Contract

## Endpoints

### `POST /api/payments/initialize`
Creates a pending order/payment, then initializes a Paystack transaction.

Request body:

```json
{
  "email": "customer@example.com",
  "user_id": "default_user",
  "currency": "USD",
  "callback_url": "http://localhost:5173/payment/callback"
}
```

Response `200`:

```json
{
  "order_id": 1,
  "reference": "SAMPLIFY-ABC123",
  "currency": "USD",
  "amount_minor": 10998,
  "authorization_url": "https://checkout.paystack.com/...",
  "access_code": "xxx",
  "status": "pending"
}
```

### `GET /api/payments/verify/{reference}`
Verifies a transaction with Paystack and updates local DB status.

Response `200`:

```json
{
  "reference": "SAMPLIFY-ABC123",
  "order_id": 1,
  "payment_status": "paid",
  "order_status": "paid",
  "currency": "USD",
  "amount_minor": 10998,
  "paid_at": "2026-03-05T14:19:03.821027+00:00"
}
```

### `POST /api/payments/webhook`
Receives Paystack events. Verifies `x-paystack-signature` and processes `charge.success`.

Response `200`:

```json
{
  "received": true,
  "reference": "SAMPLIFY-ABC123"
}
```

## Database columns

### `orders`
- `id SERIAL PRIMARY KEY`
- `user_id VARCHAR(100)`
- `email TEXT NOT NULL`
- `amount_minor BIGINT NOT NULL`
- `currency VARCHAR(3) NOT NULL`
- `status VARCHAR(20) NOT NULL DEFAULT 'pending'`
- `reference VARCHAR(120) UNIQUE NOT NULL`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `order_items`
- `id SERIAL PRIMARY KEY`
- `order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE`
- `product_id INT NOT NULL`
- `name TEXT NOT NULL`
- `unit_price_minor BIGINT NOT NULL`
- `quantity INT NOT NULL`
- `color TEXT`
- `size TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

### `payments`
- `id SERIAL PRIMARY KEY`
- `order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE`
- `reference VARCHAR(120) UNIQUE NOT NULL`
- `provider VARCHAR(50) NOT NULL DEFAULT 'paystack'`
- `status VARCHAR(20) NOT NULL DEFAULT 'pending'`
- `amount_minor BIGINT NOT NULL`
- `currency VARCHAR(3) NOT NULL`
- `paid_at TIMESTAMPTZ`
- `gateway_response JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
