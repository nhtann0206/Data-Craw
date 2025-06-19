from pydantic import BaseModel
from dotenv import load_dotenv
import os
from typing import Dict


class AppConfig:
    def __init__(self):
        load_dotenv(dotenv_path=".env", override=True)
        self.minio_host = os.getenv("MINIO_HOST")
        self.minio_port = os.getenv("MINIO_PORT")
        self.minio_access_key = os.getenv("MINIO_ROOT_USER")
        self.minio_secret_key = os.getenv("MINIO_ROOT_PASSWORD")

        self.postgres_host = os.getenv("POSTGRES_HOST")
        self.postgres_port = os.getenv("POSTGRES_PORT")
        self.postgres_user = os.getenv("POSTGRES_USER")
        self.postgres_password = os.getenv("POSTGRES_PASSWORD")
        self.postgres_db = os.getenv("POSTGRES_DB")

    def get_config(self) -> Dict[str, str]:
        return vars(self)

if __name__ == "__main__":
    config = AppConfig()
    print(config.get_config())