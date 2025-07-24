from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os
import sys

# Добавляем путь к корню проекта, чтобы импортировать app.*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импортируем db и модели
from app.extensions import db
from app.models import User, Action, ActionMark, FriendRequest, Subscriber, PotentialFriendView

# Alembic Config
config = context.config
fileConfig(config.config_file_name)

# Указываем метаданные моделей
target_metadata = db.metadata


def run_migrations_offline():
    """Миграции в оффлайн-режиме (без подключения к базе)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Миграции в онлайн-режиме (с подключением к базе)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
