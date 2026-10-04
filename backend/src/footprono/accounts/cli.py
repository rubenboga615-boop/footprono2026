"""Ligne de commande d'administration (sur le serveur).

footprono-admin make-admin +22997000000        # nommer un administrateur
footprono-admin remove-admin +22997000000
footprono-admin grant +22997000000 --days 30   # activer Premium (paiement reçu)
footprono-admin stats
footprono-admin push-test +22997000000          # notification d'essai sur ses téléphones
footprono-admin users [nom ou numéro]           # comptes existants (numéro, rôle, Premium)
footprono-admin set-phone +22997000000 +22961000000   # changer le numéro de connexion
footprono-admin reset-password +22997000000     # mot de passe provisoire
footprono-admin publish-apk footprono-apk.zip --notes "…"   # nouvelle version de l'application
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from footprono import app_release
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
            "FootProba",
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
            elif args.command == "users":
                users = await admin.search_users(session, args.query, limit=200)
                lines = [
                    f"{u.phone:<16} {u.role:<6} "
                    + (f"Premium jusqu'au {u.premium_until:%d/%m/%Y}" if u.premium_until
                       and u.premium_until > datetime.now(UTC) else "gratuit")
                    + f"  {u.display_name}" + ("" if u.is_active else "  (désactivé)")
                    for u in users
                ]  # fmt: skip
                message = "\n".join(lines) if lines else "aucun compte"
            elif args.command == "set-phone":
                user = await admin.change_phone(session, args.old, args.new)
                message = f"{user.display_name} : se connecte désormais avec {user.phone}"
            elif args.command == "reset-password":
                user, password = await admin.reset_password(session, args.phone)
                message = (
                    f"{user.display_name} ({user.phone}) : mot de passe provisoire {password}\n"
                    "À changer dans l'application : Profil → Changer le mot de passe."
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
    sub.add_parser("users", help="lister les comptes").add_argument("query", nargs="?")
    set_phone = sub.add_parser("set-phone", help="changer le numéro de connexion")
    set_phone.add_argument("old")
    set_phone.add_argument("new")
    sub.add_parser("reset-password", help="mot de passe provisoire").add_argument("phone")
    sub.add_parser("push-test", help="notification d'essai sur ses téléphones").add_argument(
        "phone"
    )
    publish = sub.add_parser("publish-apk", help="publier l'APK d'une archive GitHub Actions")
    publish.add_argument("archive", type=Path)
    publish.add_argument("--notes", default="", help="nouveautés affichées aux utilisateurs")
    publish.add_argument(
        "--minimum",
        type=int,
        default=0,
        help="construction en dessous de laquelle c'est obligatoire",
    )
    args = parser.parse_args(argv)
    if args.command == "publish-apk":
        try:
            info = app_release.publish(
                args.archive, get_settings().app_release_dir, args.notes, args.minimum
            )
        except AppError as exc:
            print(f"Erreur : {exc.message}", file=sys.stderr)
            return 1
        print(
            f"Version {info['build']} publiée ({info['size'] // 1_000_000} Mo) : proposée aux "
            "téléphones à l'ouverture de l'application."
        )
        return 0
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
