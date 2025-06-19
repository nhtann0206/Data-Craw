from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

from src.config.settings import AppConfig

class PostgresClient:

    def __init__(self, user: str, password: str, host: str, port: int, database: str):
        self.url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
        self.engine: Engine = create_engine(self.url)

    def execute_query(self, query: str, params: dict = None):
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query), params or {})
                return result.fetchall()
        except SQLAlchemyError as e:
            print("Query failed:", e)
            return None
    
    def get_records_today(self, table_name: str) -> pd.DataFrame:
        query = f"""
        SELECT * FROM {table_name}
        WHERE last_updated::date = CURRENT_DATE;
        """
        try:
            with self.engine.connect() as connection:
                result = connection.execute(query)
                records = result.fetchall()
                columns = result.keys()
                return pd.DataFrame(records, columns=columns)
        except SQLAlchemyError as e:
            print("Failed to get records for today:", e)
            return pd.DataFrame()
        
    def get_name_columns(self, table_name: str) -> list:
        query = text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """)
        try:
            with self.engine.connect() as connection:
                result = connection.execute(query, {"table_name": table_name})
                columns = [row['column_name'] for row in result.fetchall()]
                return columns
        except SQLAlchemyError as e:
            print("Failed to get column names:", e)
            return []
            
    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except SQLAlchemyError as e:
            print("Connection test failed:", e)
            return False
        
    def delete_table(self, table_name: str):
        query = f"DROP TABLE IF EXISTS {table_name};"
        try:
            with self.engine.begin() as connection:  # tự động commit khi thoát block
                connection.execute(text(query))
            print(f"Deleted {table_name}")
        except SQLAlchemyError as e:
            print("Delete failed:", e)

    def execute_non_query(self, query: str, params: dict = None):
        try:
            with self.engine.begin() as connection:
                connection.execute(text(query), params or {})
        except SQLAlchemyError as e:
            print("Execution failed:", e)
    
    def dispose(self):
        self.engine.dispose()

if __name__ == "__main__":
    config = AppConfig()
    # Example usage
    pg_client = PostgresClient(
        user=config.postgres_user,
        password=config.postgres_password,
        host="localhost",
        port=config.postgres_port,
        database=config.postgres_db
    )
    if pg_client.test_connection():
        print("Connection successful!")
    else:
        print("Connection failed.")
    

    records_today = pg_client.get_records_today("coingecko_prices")
    print("Records for today:", records_today)

    
