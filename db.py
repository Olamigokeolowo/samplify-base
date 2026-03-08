import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _db_config() -> dict[str, str | int | None]:
    return {
        "user": os.getenv("DB_USER") or os.getenv("user"),
        "password": os.getenv("DB_PASSWORD") or os.getenv("password"),
        "host": os.getenv("DB_HOST") or os.getenv("host"),
        "port": os.getenv("DB_PORT") or os.getenv("port") or 5432,
        "dbname": os.getenv("DB_NAME") or os.getenv("dbname"),
    }


def get_db_connection():
    try:
        return psycopg2.connect(**_db_config())
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None


def init_payment_tables() -> None:
    conn = get_db_connection()
    if not conn:
        return

    ddl = """
    CREATE TABLE IF NOT EXISTS orders (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(100),
        email TEXT NOT NULL,
        amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
        currency VARCHAR(3) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        reference VARCHAR(120) NOT NULL UNIQUE,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id INT NOT NULL,
        name TEXT NOT NULL,
        unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor >= 0),
        quantity INT NOT NULL CHECK (quantity > 0),
        color TEXT,
        size TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        reference VARCHAR(120) NOT NULL UNIQUE,
        provider VARCHAR(50) NOT NULL DEFAULT 'paystack',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
        currency VARCHAR(3) NOT NULL,
        paid_at TIMESTAMPTZ,
        gateway_response JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
    CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
    CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
    CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
    """

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(ddl)
    except Exception as e:
        print(f"Payment table initialization failed: {e}")
    finally:
        conn.close()


def init_auth_tables() -> None:
    conn = get_db_connection()
    if not conn:
        return

    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        gmail VARCHAR(255) NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(ddl)
    except Exception as e:
        print(f"Auth table initialization failed: {e}")
    finally:
        conn.close()
