"""Détection des doublons : un composant décrit deux fois sous des libellés différents.

Trois niveaux, du plus sûr au moins sûr :
1. référence fabricant identique une fois normalisée : certitude 100 % ;
2. code de référence (lettres et chiffres mêlés, 5 caractères au moins) d'un composant cité
   dans le texte de l'autre : 95 % ;
3. similarité des libellés (difflib) : fusion proposée à 0,85, simple signalement à 0,70.
   Garde numérique : si les nombres des deux libellés diffèrent (12 V contre 24 V), jamais
   de fusion, seulement un signalement.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

SEUIL_FUSION = 0.85
SEUIL_SIGNALEMENT = 0.70
SCORE_REFERENCE_CITEE = 0.95
NB_CANDIDATS = 3
LONGUEUR_CODE = 5

# Références de remplissage, jamais prises pour une vraie référence.
REMPLISSAGES: frozenset[str] = frozenset({"", "adefinir", "afaire", "nc", "na", "tbd", "inconnu"})


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, sans espaces, tirets, points, barres, parenthèses ni _."""
    if not texte:
        return ""
    decompose = unicodedata.normalize("NFKD", str(texte).lower())
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return re.sub(r"[\s\-./\\()_]", "", sans_accents)


def codes(*textes: str | None) -> set[str]:
    """Codes de référence contenus dans les textes (mcp2562, as5047d, ina260…)."""
    trouves = set()
    for texte in textes:
        for morceau in re.split(r"[\s/,;()+]+", texte or ""):
            candidats = {normaliser(morceau), *(normaliser(p) for p in re.split(r"[-._]", morceau))}
            for code in candidats:
                if (
                    len(code) >= LONGUEUR_CODE
                    and re.search(r"[a-z]", code)
                    and re.search(r"\d", code)
                ):
                    trouves.add(code)
    return trouves


def nombres(*textes: str | None) -> set[str]:
    """Nombres cités dans les libellés, pour la garde numérique."""
    trouves = set()
    for texte in textes:
        for nombre in re.findall(r"\d+(?:[.,]\d+)?", texte or ""):
            trouves.add(nombre.replace(",", ".").rstrip("0").rstrip(".") or "0")
    return trouves


@dataclass
class Empreinte:
    """Ce qui sert à comparer un composant (existant ou ligne importée)."""

    cle: Any
    reference: str
    codes: set[str]
    texte: str
    libelle: str
    designation: str
    nombres: set[str]


def empreinte(cle: Any, valeurs: dict[str, Any]) -> Empreinte:
    fonction = valeurs.get("fonction")
    designation = valeurs.get("designation")
    reference = valeurs.get("ref_fabricant")
    ref = normaliser(reference)
    return Empreinte(
        cle=cle,
        reference="" if ref in REMPLISSAGES else ref,
        codes=codes(reference, designation),
        texte=normaliser(fonction) + normaliser(designation) + ref,
        libelle=normaliser(fonction) + normaliser(designation),
        designation=normaliser(designation),
        nombres=nombres(fonction, designation),
    )


def _similarite(a: Empreinte, b: Empreinte) -> float:
    ratios = [
        SequenceMatcher(None, x, y).ratio()
        for x, y in ((a.libelle, b.libelle), (a.designation, b.designation))
        if x and y
    ]
    return max(ratios, default=0.0)


def compare(ligne: Empreinte, existant: Empreinte) -> dict | None:
    """Niveau, score et possibilité de fusion ; None si les deux n'ont rien de commun."""
    if ligne.reference and ligne.reference == existant.reference:
        return {"niveau": 1, "score": 1.0, "fusion": True, "motif": "référence fabricant identique"}
    cite = {c for c in existant.codes if c in ligne.texte} | {
        c for c in ligne.codes if c in existant.texte
    }
    if cite:
        motif = f"référence « {sorted(cite)[0]} » citée dans le libellé"
        return {"niveau": 2, "score": SCORE_REFERENCE_CITEE, "fusion": True, "motif": motif}
    ratio = _similarite(ligne, existant)
    if ratio < SEUIL_SIGNALEMENT:
        return None
    garde = bool(ligne.nombres and existant.nombres and ligne.nombres != existant.nombres)
    motif = f"libellés proches ({round(ratio * 100)} %)"
    if garde:
        motif += " mais valeurs numériques différentes"
    return {
        "niveau": 3,
        "score": round(ratio, 3),
        "fusion": ratio >= SEUIL_FUSION and not garde,
        "motif": motif,
    }


def search(ligne: Empreinte, existants: list[Empreinte]) -> list[dict]:
    """Les meilleurs candidats, du plus sûr au moins sûr."""
    trouves = []
    for existant in existants:
        resultat = compare(ligne, existant)
        if resultat:
            trouves.append({"cle": existant.cle, **resultat})
    trouves.sort(key=lambda c: (-c["fusion"], c["niveau"], -c["score"]))
    return trouves[:NB_CANDIDATS]
