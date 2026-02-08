#!/usr/bin/env python3
"""Script to create an admin user."""

import asyncio
import sys
from getpass import getpass

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.models import Base
from app.models.user import User, UserRole


async def create_admin():
    """Create an admin user interactively."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if admin already exists
        result = await session.execute(
            select(User).where(User.role == UserRole.ADMIN)
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print(f"Un admin existe déjà: {existing_admin.email}")
            overwrite = input("Voulez-vous créer un nouvel admin ? (o/N): ")
            if overwrite.lower() != "o":
                print("Opération annulée.")
                return

        # Get admin details
        print("\n=== Création d'un utilisateur admin ===\n")
        email = input("Email: ").strip()
        if not email:
            print("Email requis.")
            return

        password = getpass("Mot de passe (min 8 caractères): ")
        if len(password) < 8:
            print("Le mot de passe doit contenir au moins 8 caractères.")
            return

        password_confirm = getpass("Confirmer le mot de passe: ")
        if password != password_confirm:
            print("Les mots de passe ne correspondent pas.")
            return

        first_name = input("Prénom (optionnel): ").strip() or None
        last_name = input("Nom (optionnel): ").strip() or None

        # Check if email already exists
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"Un utilisateur avec l'email {email} existe déjà.")
            return

        # Create admin user
        admin = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )

        session.add(admin)
        await session.commit()

        print(f"\n✅ Admin créé avec succès!")
        print(f"   Email: {email}")
        print(f"   Rôle: admin")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
