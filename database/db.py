from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "finance.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def init_db():
    # Import models so SQLAlchemy registers them with Base.metadata
    from database import models

    Base.metadata.create_all(bind=engine)