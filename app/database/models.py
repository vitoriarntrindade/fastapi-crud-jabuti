"""SQLAlchemy ORM model for the users table."""

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base

__all__ = ["Base", "User"]


class User(Base):
    """Represents a user record in the PostgreSQL database."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
