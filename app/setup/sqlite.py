"""
Module to setup Sqlite databases and tables.
Applies migrations.
"""

from sqlalchemy import create_engine
from app.db.userdata import UserTable
from app.db.sqlite.auth import SQLiteAuthMethods as authdb
from app.migrations import apply_migrations
from app.settings import Db

from app.db import create_all
from app.db.libdata import create_all as create_all_libdata

from app.db.engine import DbEngine


def run_migrations():
    """
    Run migrations and updates migration version.
    """
    apply_migrations()


def setup_sqlite():
    """
    Create Sqlite databases and tables.
    """
    DbEngine.engine = create_engine(
        f"sqlite+pysqlite:///{Db.get_app_db_path()}",
        echo=False,
        max_overflow=20,
        pool_size=10,
    )

    create_all()
    create_all_libdata()

    if not UserTable.get_all():
        UserTable.insert_default_user()
