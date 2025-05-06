# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = None
SessionLocal = None
if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        print("Database engine and session factory configured successfully.")
    except Exception as e:
        print(f"!!! Error creating database engine or session factory: {e}")
else:
     print("!!! คำเตือน: ไม่พบค่า DATABASE_URL ใน environment variable")
Base = declarative_base()
def get_db():
    if SessionLocal is None: raise Exception("Database session factory (SessionLocal) is not configured.")
    db = SessionLocal()
    try: yield db
    finally: db.close()