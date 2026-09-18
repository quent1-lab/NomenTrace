"""Exceptions métier, traduites en {"erreur": "..."} par l'application."""


class ErreurMetier(Exception):
    """Refus métier explicite, avec son message en français et son code HTTP."""

    def __init__(self, message: str, statut: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.statut = statut


class Introuvable(ErreurMetier):
    """La ressource demandée n'existe pas (ou est archivée)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 404)


class Conflit(ErreurMetier):
    """L'opération entre en conflit avec l'état de la base."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 409)
