"""Modèles Pydantic de validation des requêtes et des réponses de l'API."""

from pydantic import BaseModel


class SanteReponse(BaseModel):
    """État de l'application renvoyé par GET /api/sante."""

    statut: str
    version_schema: int
    nom_projet: str | None
