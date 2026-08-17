"""Configuration du service IA (chargée depuis l'environnement / .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Clé API Claude (server-side uniquement, jamais exposée)
    anthropic_api_key: str = ""
    # Secret partagé backend <-> IA (authentification service-à-service)
    internal_api_key: str = "dev-secret-change-me"

    ai_env: str = "development"
    default_max_tokens: int = 1024

    # Clés des sources de prospection (server-side uniquement).
    # Absentes = le sourcing reste utilisable en mode simulation (dry_run).
    apollo_api_key: str = ""
    google_places_api_key: str = ""
    hunter_api_key: str = ""
    # Plafond de coût cumulé par workspace ($) avant blocage (0 = illimité)
    max_cost_per_workspace: float = 0.0


# Table de routage : capacité logique -> modèle Claude réel (CDCF §5.1)
TIER_TO_MODEL = {
    "fast": "claude-haiku-4-5",       # volume / faible latence : classification
    "reasoning": "claude-sonnet-4-6",  # raisonnement : qualification, génération
}

# Prix en $ / 1M tokens : (input, output)
MODEL_PRICING = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()
