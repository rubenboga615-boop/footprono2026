"""Suppression du compte par son titulaire (exigée par Google Play et l'App Store).

Effacés : numéro, nom, mot de passe, portefeuille fictif et mouvements, paris,
montantes, notifications, téléphones enregistrés, historique Premium.
Conservés sans lien avec la personne (obligation comptable) : les paiements
(montant, devise, date, référence du prestataire) ; la réponse brute du
prestataire, qui peut contenir un nom ou un numéro, est vidée.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import User
from footprono.accounts.security import verify_password
from footprono.accounts.service import UnauthorizedError
from footprono.core.errors import AppError
from footprono.payments.models import Payment


async def delete_account(session: AsyncSession, user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("mot de passe incorrect")
    if user.role == "admin":
        admins = await session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if (admins or 0) <= 1:
            raise AppError("dernier administrateur : nommer un autre administrateur d'abord")
    await session.execute(
        update(Payment)
        .where(Payment.user_id == user.id, Payment.status == "pending")
        .values(status="cancelled")
    )
    await session.execute(
        update(Payment).where(Payment.user_id == user.id).values(raw={}, payment_url=None)
    )
    # Le reste part en cascade (ON DELETE CASCADE) ; les paiements passent à NULL.
    user_id = user.id
    session.expunge(user)
    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()
