import pathlib

from data.database import get_session_factory

ROOT = pathlib.Path(__file__).parent.parent
DB_PATH = f"sqlite:///{ROOT / 'jra_data.db'}"


def get_db():
    session = get_session_factory(DB_PATH)()
    try:
        yield session
    finally:
        session.close()
