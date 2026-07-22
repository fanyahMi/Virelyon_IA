"""Authentification service-à-service : seul le backend (qui détient le secret
partagé) peut appeler le service IA. Comparaison en temps constant (anti timing-attack)."""
import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def verify_caller(
    x_internal_key: str = Header(default="", alias="X-Internal-Key"),
) -> bool:
    expected = get_settings().internal_api_key
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Appelant non autorisé (X-Internal-Key manquante ou invalide).",
        )
    return True
