"""Schémas communs (métadonnées de réponse)."""
from pydantic import BaseModel


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class Meta(BaseModel):
    """Métadonnées jointes à chaque réponse issue d'un appel LLM."""
    model_used: str
    usage: Usage
    cost_estimate: float
    cached: bool = False  # True si la réponse vient du cache (coût 0)
