"""Contrôle de la forme des champs texte d'un composant.

Deux niveaux. Une erreur évidente (une adresse web collée dans la référence fabricant, un
retour à la ligne dans une référence) est refusée à la saisie, mais seulement sur les champs
que l'écriture touche : un composant déjà mal rempli reste modifiable sur ses autres champs.
Une saisie seulement inhabituelle (référence très longue, qui ressemble à une phrase) n'est
jamais refusée : l'écran Nettoyage la signale, avec les erreurs déjà en base.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from backend.erreurs import ErreurMetier

# Champs texte qui ne sont pas des liens, avec leur libellé.
TEXTES: dict[str, str] = {
    "fonction": "Fonction",
    "designation": "Désignation",
    "ref_fabricant": "Réf fabricant",
    "fabricant": "Fabricant",
}
# Au-delà, une référence fabricant est signalée : les plus longues tiennent en 30 caractères.
LONGUEUR_REF: int = 40
# À partir de ce nombre de mots, une référence ressemble à une description.
MOTS_REF: int = 4

_ADRESSE_WEB = re.compile(
    r"https?://|www\.|\b[a-z0-9-]+\.(?:com|fr|net|org|io|eu|de|co\.uk|cn)/", re.IGNORECASE
)


def erreurs(valeurs: Mapping[str, Any], touches: Iterable[str] | None = None) -> list[str]:
    """Erreurs évidentes, qui font refuser la saisie, sur les champs touchés (tous si None)."""
    champs = TEXTES if touches is None else {c: TEXTES[c] for c in touches if c in TEXTES}
    messages = []
    for champ, libelle in champs.items():
        texte = valeurs.get(champ)
        if not isinstance(texte, str) or not texte:
            continue
        if _ADRESSE_WEB.search(texte):
            messages.append(
                f"{libelle} : une adresse web n'a rien à faire ici (champ Lien produit)"
            )
        elif champ == "ref_fabricant" and ("\n" in texte or "\r" in texte):
            messages.append(f"{libelle} : pas de retour à la ligne dans une référence")
    return messages


def avertissements(valeurs: Mapping[str, Any]) -> list[str]:
    """Saisies inhabituelles, signalées sans être refusées."""
    reference = valeurs.get("ref_fabricant")
    if not isinstance(reference, str) or not reference:
        return []
    if len(reference) > LONGUEUR_REF:
        return [f"Réf fabricant de plus de {LONGUEUR_REF} caractères"]
    if len(reference.split()) >= MOTS_REF:
        return ["Réf fabricant qui ressemble à une description"]
    return []


def a_verifier(valeurs: Mapping[str, Any]) -> list[str]:
    """Tout ce que l'écran Nettoyage signale pour un composant : erreurs puis avertissements."""
    return erreurs(valeurs) + avertissements(valeurs)


def verifier(valeurs: Mapping[str, Any], touches: Iterable[str] | None = None) -> None:
    """Refuse l'écriture si un champ touché porte une erreur évidente."""
    trouvees = erreurs(valeurs, touches)
    if trouvees:
        raise ErreurMetier("Saisie refusée. " + " ; ".join(trouvees) + ".")
