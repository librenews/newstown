"""User store for authentication."""
from typing import Optional, Dict, Any
from uuid import UUID
from db.connection import db
from api.auth import get_password_hash

class UserStore:
    """Handles user data persistence."""

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user by their username."""
        row = await db.fetchrow(
            "SELECT * FROM users WHERE username = $1",
            username
        )
        return dict(row) if row else None

    async def create_user(self, username: str, password: str, role: str = "viewer") -> UUID:
        """Create a new user with a hashed password."""
        password_hash = get_password_hash(password)
        user_id = await db.fetchval(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            username, password_hash, role
        )
        return user_id

    async def ensure_admin_exists(self, username: str = "admin", password: str = "admin123"):
        """Ensure at least one admin user exists."""
        user = await self.get_user_by_username(username)
        if not user:
            await self.create_user(username, password, role="admin")
            return True
        return False

# Global instance
user_store = UserStore()
