"""Ligne de commande d'administration (sur le serveur).

footprono-admin make-admin +22997000000        # nommer un administrateur
footprono-admin remove-admin +22997000000
footprono-admin grant +22997000000 --days 30   # activer Premium (paiement reçu)
footprono-admin stats
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from sqlalchemy import select

from footprono.accounts import admin
from footprono.accounts.models import User
from footprono.accounts.service import normalize_phone
from footprono.core.config import get_settings
from footprono.core.errors import AppError
from footprono.db.session import create_engine, create_session_factory


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
    args = parser.parse_args(argv)
    try:
        print(asyncio.run(_run(args)))
    except AppError as exc:
        print(f"Erreur : {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
