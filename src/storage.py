import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "localhost")
PORT = os.getenv("MYSQL_PORT", "3306")
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DB", "brand_visibility_db")


def get_engine(include_db: bool = True):
    """Create a SQLAlchemy engine for MySQL."""
    db_part = f"/{DB_NAME}" if include_db else ""
    url = f"mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}{db_part}"
    return create_engine(url)


def init_database():
    """Create the MySQL database if it does not already exist."""
    engine = get_engine(include_db=False)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME};"))
        conn.commit()
    print(f"Database '{DB_NAME}' is ready.")


def load_csv_to_mysql():
    """Load processed CSV files into MySQL tables."""
    init_database()
    engine = get_engine(include_db=True)

    # 1. Load product-level featured data
    df_products = pd.read_csv("data/Processed/featured_brand_visibility.csv")
    df_products.to_sql(
        name="product_listings",
        con=engine,
        if_exists="replace",
        index=False,
    )
    print(f"Loaded {len(df_products)} rows into 'product_listings'.")


def fetch_table(query: str) -> pd.DataFrame:
    """Run a SQL SELECT query and return a pandas DataFrame."""
    engine = get_engine(include_db=True)
    with engine.connect() as conn:
        return pd.read_sql(text(query), con=conn)


if __name__ == "__main__":
    load_csv_to_mysql()
