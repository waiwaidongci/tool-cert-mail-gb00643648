from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from src.config.settings import DB_URL

class Base(DeclarativeBase):
    pass

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=240)
Session = sessionmaker(engine, expire_on_commit=False)


def connection():
    with Session() as db:
        yield db


def prepare_columns():
    """只补建可空/带默认值的新列；修改字段口径仍走显式迁移。"""
    additions = {
        'datasets': {'kind': "VARCHAR(20) NOT NULL DEFAULT 'certificate'"},
        'runs': {
            'kind': "VARCHAR(20) NOT NULL DEFAULT 'certificate'",
            'previous_run_id': 'INT NULL',
        },
        'schedules': {'kind': "VARCHAR(20) NOT NULL DEFAULT 'certificate'"},
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {column['name'] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))
