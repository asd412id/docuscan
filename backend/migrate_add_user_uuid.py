"""
Migration script to add uuid column to users table.
Run this once to update existing database.

Usage:
    python migrate_add_user_uuid.py
"""

import asyncio
import uuid as uuid_lib
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def migrate():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    async with engine.begin() as conn:
        # Check if column already exists
        if "postgresql" in settings.database_url:
            result = await conn.execute(
                text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='users' AND column_name='uuid'
                """)
            )
            exists = result.fetchone() is not None
        else:
            # SQLite
            result = await conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            exists = "uuid" in columns

        if exists:
            print("Column 'uuid' already exists in users table. Skipping.")
            return

        print("Adding 'uuid' column to users table...")

        # Add column (nullable first)
        if "postgresql" in settings.database_url:
            await conn.execute(text("ALTER TABLE users ADD COLUMN uuid VARCHAR(36)"))
        else:
            await conn.execute(text("ALTER TABLE users ADD COLUMN uuid VARCHAR(36)"))

        # Generate UUIDs for existing users
        result = await conn.execute(text("SELECT id FROM users"))
        users = result.fetchall()

        for user in users:
            user_uuid = str(uuid_lib.uuid4())
            await conn.execute(
                text("UPDATE users SET uuid = :uuid WHERE id = :id"),
                {"uuid": user_uuid, "id": user[0]},
            )
            print(f"  User {user[0]} -> {user_uuid}")

        # Add unique constraint and index
        if "postgresql" in settings.database_url:
            await conn.execute(text("ALTER TABLE users ALTER COLUMN uuid SET NOT NULL"))
            await conn.execute(
                text("ALTER TABLE users ADD CONSTRAINT users_uuid_unique UNIQUE (uuid)")
            )
            await conn.execute(text("CREATE INDEX ix_users_uuid ON users (uuid)"))
        else:
            # SQLite doesn't support ALTER COLUMN, but we can add index
            await conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_uuid ON users (uuid)")
            )

        print("Migration completed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
