# alembic/env.py
import os
import sys
from logging.config import fileConfig
from sqlalchemy import create_engine
from alembic import context
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..')) # PROJECT_ROOT คือ gofresh_stockpro

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from database import Base
    import models
    print("Successfully imported Base and models for Alembic.")
    target_metadata = Base.metadata
except ImportError as e:
    print(f"Error importing Base or models for Alembic: {e}")
    print(f"Current sys.path: {sys.path}")
    Base = None
    target_metadata = None

dotenv_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(dotenv_path): load_dotenv(dotenv_path)
else: print(f"Warning: .env file not found at {dotenv_path}")

config = context.config
if config.config_file_name is not None: fileConfig(config.config_file_name)

if Base: target_metadata = Base.metadata
else: target_metadata = None

def run_migrations_offline() -> None:
    url = os.getenv("DATABASE_URL")
    if not url: raise ValueError("DATABASE_URL not set for offline mode.")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url: raise ValueError("DATABASE_URL not set.")
    connectable = create_engine(db_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()