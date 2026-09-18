"""Arrondi des valeurs renvoyées : appliqué une seule fois, à la sortie de l'API ou de l'export."""

from typing import Any

DECIMALES: int = 2


def round_value(cle: str, valeur: Any) -> Any:
    """Arrondit un réel à deux décimales, sauf les taux (0.055 doit rester 0.055)."""
    if isinstance(valeur, float) and not cle.startswith("taux"):
        return round(valeur, DECIMALES)
    return valeur


def round_output(donnees: Any) -> Any:
    """Arrondit récursivement les réels d'un dictionnaire ou d'une liste de dictionnaires."""
    if isinstance(donnees, list):
        return [round_output(element) for element in donnees]
    if isinstance(donnees, dict):
        return {
            cle: round_output(v) if isinstance(v, dict | list) else round_value(cle, v)
            for cle, v in donnees.items()
        }
    return donnees
