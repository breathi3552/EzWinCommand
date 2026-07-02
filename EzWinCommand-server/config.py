"""配置管理：读取 .env 并提供默认值。"""
import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
BEARER_TOKEN = os.getenv("BEARER_TOKEN", "")
