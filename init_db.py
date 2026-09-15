from database.db import Base, engine

# This import is important.
# SQLAlchemy needs to know about your models.
from database import models


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")


if __name__ == "__main__":
    init_db()