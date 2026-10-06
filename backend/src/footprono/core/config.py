"""Configuration de l'application.

Toute la configuration vient des variables d'environnement (préfixe ``FP_``),
éventuellement chargées depuis un fichier ``.env``. En production, les secrets
sont obligatoires : l'application refuse de démarrer plutôt que de tourner avec
une valeur par défaut prévisible.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SECRET_LENGTH = 32


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "FootProba"
    api_prefix: str = "/api/v1"

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://footprono:footprono@localhost:5432/footprono"),
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)

    redis_url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))
    celery_broker_url: RedisDsn | None = None
    celery_result_backend: RedisDsn | None = None

    secret_key: SecretStr | None = None
    api_football_key: SecretStr | None = None
    # Requêtes API-Football au plus par fichier (une ligue, une saison) téléchargé.
    api_football_budget: int = Field(default=1500, ge=1)
    # Marge quotidienne de sécurité : la collecte s'arrête sous ce nombre de
    # requêtes restantes (garde de quoi suivre les matchs en direct).
    api_football_min_remaining: int = Field(default=200, ge=0)
    # Bookmakers dont les cotes des matchs à venir sont collectées (noms
    # API-Football). Pinnacle sert de référence interne, il n'est pas affiché.
    odds_bookmakers: list[str] = Field(default_factory=lambda: ["1xBet", "Bet365", "Pinnacle"])
    cors_origins: list[str] = Field(default_factory=list)
    # Version web de l'application (dossier « build/web » de Flutter, construit
    # avec --base-href /app/) : servie sur /app, à la même adresse que l'API.
    web_app_dir: Path | None = None
    # Clé du compte de service Firebase (JSON, secret) : notifications sur le
    # téléphone fermé. Vide : pas de notifications push.
    fcm_credentials_file: Path | None = None
    # Notifications de la version web (iPhone : FootProba ajouté à l'écran d'accueil) :
    # clé publique « Web Push » (Firebase → Paramètres du projet → Cloud Messaging →
    # Certificats Web Push). Vide : pas de notifications sur la version web.
    web_push_vapid_key: str | None = None
    # Adresse publique du serveur (https://…) : retour et notification de paiement.
    public_url: str | None = None
    # Paiement Mobile Money (CinetPay, espace marchand → Intégrations).
    # Sans clé : le paiement est indisponible (Premium par l'administrateur).
    cinetpay_api_key: SecretStr | None = None
    cinetpay_site_id: str | None = None
    # Paystack (tableau de bord → Settings → API Keys & Webhooks), secret. Si elle est
    # définie, Paystack est le prestataire des nouveaux paiements (sinon CinetPay).
    paystack_secret_key: SecretStr | None = None
    # Wave Business (Checkout API), clé secrète : paiement depuis l'application Wave.
    wave_api_key: SecretStr | None = None
    # Paiement Wave « à la main » en attendant un compte marchand : numéro Wave qui
    # reçoit les 2 000 F ; l'administrateur vérifie la réception puis offre Premium.
    wave_manual_number: str | None = None
    # Connexion avec Google (Firebase Authentication) : identifiant public du projet
    # Firebase, celui de l'application. Vide : connexion Google indisponible.
    firebase_project_id: str | None = "footprono-56616"
    # Aide aux joueurs (bouton « Aide » et « Mot de passe oublié ») : numéro WhatsApp
    # public, format international.
    support_whatsapp: str | None = "+2250500649904"
    # Alertes de l'administrateur (application ntfy) : serveur de publication.
    alerts_ntfy_url: str = "https://ntfy.sh"

    # Comptes et bookmaker virtuel (argent fictif, montants entiers en devise).
    access_token_days: int = Field(default=30, ge=1)
    # Console : code de sécurité (application d'authentification) obligatoire ; sans
    # lui, seule la page Sécurité est ouverte pour l'activer.
    console_require_totp: bool = True
    starting_balance: int = Field(default=100_000, ge=0)
    # Rechargement gratuit : jusqu'au solde de départ, si le solde est sous ce
    # seuil, au plus une fois par intervalle.
    refill_below: int = Field(default=1_000, ge=0)
    refill_interval_days: int = Field(default=7, ge=1)

    # Tentatives : échecs de connexion par numéro et par adresse IP (15 min),
    # inscriptions par adresse IP (1 h). 0 : pas de limite (tests).
    login_failures_per_phone: int = Field(default=10, ge=0)
    login_failures_per_ip: int = Field(default=50, ge=0)
    registrations_per_ip: int = Field(default=10, ge=0)

    # Fichiers bruts archivés (football-data, Understat…), nommés par empreinte.
    raw_data_dir: Path = Path("data/raw")
    # Archive de l'historique API-Football (collecte de la console, import) ; « ~ » accepté.
    history_archive_dir: Path = Path("~/storage/downloads/api-football-historique")
    # Fichiers produits par la console (exports, rapports, archives), gardés 30 jours.
    console_files_dir: Path = Path("data/console-files")
    # Sauvegardes de la base (lecture seule : dernière sauvegarde au tableau de bord).
    backups_dir: Path | None = None
    # Politique de confidentialité (/confidentialite) : identité et contact du responsable.
    legal_name: str = "FootProba (société en cours d'immatriculation)"
    contact_email: str = "[adresse e-mail à compléter]"
    privacy_hosting: str = (
        "Hetzner Online GmbH (Allemagne), serveur à Helsinki, Finlande (Union européenne)"
    )
    privacy_payment_provider: str = "Paystack"
    backup_keep_days: int = Field(default=14, ge=1)
    # APK publié par « footprono-admin publish-apk » (mise à jour de l'application).
    app_release_dir: Path = Path("data/app")
    # Version web publiée depuis la console (« footprono-admin publish-web ») : servie sur
    # /app sauf si FP_WEB_APP_DIR désigne un dossier fixe.
    web_release_dir: Path = Path("data/web")

    log_level: str = "INFO"
    log_json: bool = True

    # Délai maximal d'une vérification de dépendance (base, Redis) dans /ready.
    readiness_timeout_seconds: float = Field(default=2.0, gt=0)

    @field_validator(
        "web_app_dir",
        "fcm_credentials_file",
        "web_push_vapid_key",
        "public_url",
        "cinetpay_api_key",
        "cinetpay_site_id",
        "paystack_secret_key",
        "wave_api_key",
        "wave_manual_number",
        "firebase_project_id",
        "support_whatsapp",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        # « FP_WEB_APP_DIR= » (vide) dans .env : pas de version web (idem pour la clé Firebase).
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            secret = self.secret_key.get_secret_value() if self.secret_key else ""
            if len(secret) < _MIN_SECRET_LENGTH:
                raise ValueError(
                    f"FP_SECRET_KEY est obligatoire en production "
                    f"({_MIN_SECRET_LENGTH} caractères minimum)"
                )
            if "*" in self.cors_origins:
                raise ValueError("FP_CORS_ORIGINS ne peut pas contenir '*' en production")
        return self

    @property
    def broker_url(self) -> str:
        return str(self.celery_broker_url or self.redis_url)

    @property
    def result_backend(self) -> str:
        return str(self.celery_result_backend or self.redis_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
