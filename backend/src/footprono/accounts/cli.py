"""Ligne de commande d'administration (sur le serveur).

footprono-admin make-admin +22997000000        # nommer un administrateur
footprono-admin remove-admin +22997000000
footprono-admin grant +22997000000 --days 30   # activer Premium (paiement reçu)
footprono-admin stats
footprono-admin push-test +22997000000          # notification d'essai sur ses téléphones
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono.accounts import admin
from footprono.accounts.models import User
from footprono.accounts.service import normalize_phone
from footprono.core.config import get_settings
from footprono.core.errors import AppError
from footprono.db.session import create_engine, create_session_factory
from footprono.notifications import push


async def _push_test(session: AsyncSession, phone: str) -> str:
    settings = get_settings()
    sender = push.FcmSender.from_settings(settings)
    if sender is None:
        raise AppError("notifications push désactivées : FP_FCM_CREDENTIALS_FILE non défini")
    user = await session.scalar(select(User).where(User.phone == normalize_phone(phone)))
    if user is None:
        raise AppError(f"aucun compte avec le numéro {phone}")
    try:
        result = await sender.send_to_user(
            session,
            user.id,
            "FootProno",
            "Notification d'essai : tout fonctionne.",
            {"kind": "test"},
        )
    finally:
        await sender.aclose()
    if result.sent == 0 and result.removed == 0 and result.failed == 0:
        raise AppError(
            f"aucun téléphone enregistré pour {user.phone} : ouvre l'application "
            "Android sur ce compte et accepte les notifications"
        )
    return (
        f"{user.display_name} : {result.sent} envoyée(s), {result.failed} en échec, "
        f"{result.removed} téléphone(s) oublié(s) (jeton périmé)"
    )


async def _run(args: argparse.Namespace) -> str:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            if args.command in ("make-admin", "remove-admin"):
                role = "admin" if args.command == "make-admin" else "user"
                user = await admin.set_role(session, args.phone, role)
                message = f"{user.display_name} ({user.phone}) : rôle {user.role}"
            elif args.command == "grant":
                found = await session.scalar(
                    select(User).where(User.phone == normalize_phone(args.phone))
                )
                if found is None:
                    raise AppError(f"aucun compte avec le numéro {args.phone}")
                await admin.grant_premium(session, None, found, args.days, note=args.note)
                message = f"{found.display_name} ({found.phone}) : Premium jusqu'au " + (
                    f"{found.premium_until:%d/%m/%Y %H:%M} (UTC)"
                )
            elif args.command == "push-test":
                message = await _push_test(session, args.phone)
            else:
                message = json.dumps(await admin.stats(session), indent=2, ensure_ascii=False)
            await session.commit()
            return message
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footprono-admin")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_ in (("make-admin", "nommer administrateur"), ("remove-admin", "retirer")):
        sub.add_parser(name, help=help_).add_argument("phone")
    grant = sub.add_parser("grant", help="activer Premium")
    grant.add_argument("phone")
    grant.add_argument("--days", type=int, default=30)
    grant.add_argument("--note")
    sub.add_parser("stats", help="nombre de comptes, Premium, paris")
    sub.add_parser("push-test", help="notification d'essai sur ses téléphones").add_argument(
        "phone"
    )
    args = parser.parse_args(argv)
    try:
        print(asyncio.run(_run(args)))
    except AppError as exc:
        print(f"Erreur : {exc.message}", file=sys.stderr)
        return 1
    except push.PushConfigError as exc:
        print(f"Erreur Firebase : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
