"""Journal des actions d'administration : chaque modification faite depuis la
console (comptes, Premium, rôles, tâches, versions, sécurité) laisse une ligne."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts.models import AdminAction, User


def record(
    session: AsyncSession,
    admin: User | None,
    action: str,
    summary: str,
    target: User | int | None = None,
) -> None:
    """Ajoute une ligne (écrite avec la transaction de l'action elle-même)."""
    target_id = target.id if isinstance(target, User) else target
    session.add(
        AdminAction(
            admin_id=admin.id if admin else None,
            action=action[:40],
            target_user_id=target_id,
            summary=summary[:300],
        )
    )


def who(user: User) -> str:
    return f"{user.display_name} ({user.phone or user.email or f'compte {user.id}'})"


async def recent(session: AsyncSession, limit: int = 200) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(AdminAction, User.display_name)
        .outerjoin(User, User.id == AdminAction.admin_id)
        .order_by(AdminAction.id.desc())
        .limit(limit)
    )
    return [
        {
            "id": a.id,
            "at": a.created_at,
            "admin": name or "compte supprimé",
            "action": a.action,
            "summary": a.summary,
            "target_user_id": a.target_user_id,
        }
        for a, name in rows.all()
    ]
