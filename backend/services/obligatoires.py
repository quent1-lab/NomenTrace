"""Champs obligatoires d'un composant, réglés dans les paramètres.

Deux sources : des champs de base choisis parmi CHAMPS (paramètre `champs_obligatoires`) et
les attributs marqués obligatoires. La portée (`champs_obligatoires_portee`) limite la règle
aux composants en mode Achat, par défaut, ou l'étend à tous.

La règle s'applique à la création d'un composant, et à toute modification qui touche un champ
obligatoire ou fait entrer le composant dans la portée. Un composant déjà incomplet reste
modifiable sur ses autres champs : une règle ajoutée après coup ne bloque pas l'existant, que
l'écran Nettoyage signale.
"""

import sqlite3
from collections.abc import Iterable

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import attributs, parametres

# Champs de base qui peuvent être rendus obligatoires, avec leur libellé.
CHAMPS: dict[str, str] = {
    "lien_produit": "Lien produit",
    "fournisseur_nom": "Fournisseur",
    "ref_fabricant": "Réf fabricant",
    "fabricant": "Fabricant",
    "pu_releve": "PU relevé",
}
PORTEES: tuple[str, ...] = ("achat", "tous")
PORTEE_DEFAUT = "achat"
MODE_ACHAT = "Achat"


def champs_requis(conn: sqlite3.Connection) -> list[str]:
    """Champs de base obligatoires, dans l'ordre de CHAMPS."""
    texte = parametres.get_parametre(conn, "champs_obligatoires") or ""
    choisis = {c.strip() for c in texte.split(",") if c.strip()}
    return [c for c in CHAMPS if c in choisis]


def portee(conn: sqlite3.Connection) -> str:
    valeur = parametres.get_parametre(conn, "champs_obligatoires_portee")
    return valeur if valeur in PORTEES else PORTEE_DEFAUT


def attributs_requis(conn: sqlite3.Connection) -> dict[str, str]:
    """Attributs actifs et obligatoires : {code: libellé}."""
    lignes = db.fetch_all(
        conn,
        "SELECT code, libelle FROM attribut WHERE obligatoire = 1 AND actif = 1 ORDER BY ordre",
    )
    return {ligne["code"]: ligne["libelle"] for ligne in lignes}


def _vide(valeur: object) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def manquants(conn: sqlite3.Connection, composant: dict, valeurs_attributs: dict) -> dict[str, str]:
    """Champs obligatoires vides du composant : {clé: libellé}, clé « attr:code » d'un attribut."""
    if portee(conn) == PORTEE_DEFAUT and composant.get("mode_appro") != MODE_ACHAT:
        return {}
    resultat = {c: CHAMPS[c] for c in champs_requis(conn) if _vide(composant.get(c))}
    for code, libelle in attributs_requis(conn).items():
        if _vide(valeurs_attributs.get(code)):
            resultat[f"{attributs.PREFIXE_CHAMP}{code}"] = libelle
    return resultat


def verifier(conn: sqlite3.Connection, identifiant: str, touches: Iterable[str] | None) -> None:
    """Refuse l'écriture qui laisse un champ obligatoire vide, dans la transaction en cours.

    touches : clés écrites (champs, ou « attr:code »), None pour une création. Hors création,
    seuls comptent les champs touchés, sauf changement de mode d'approvisionnement, qui fait
    entrer le composant dans la règle tout entière.
    """
    composant = db.fetch_one(conn, "SELECT * FROM composant WHERE id = ?", (identifiant,))
    if composant is None:
        return
    vides = manquants(conn, composant, attributs.get_valeurs(conn, identifiant))
    if touches is not None:
        touches = set(touches)
        if "mode_appro" not in touches:
            vides = {cle: libelle for cle, libelle in vides.items() if cle in touches}
    if vides:
        portee_texte = "" if portee(conn) == "tous" else " en mode Achat"
        raise ErreurMetier(
            f"Champs obligatoires pour un composant{portee_texte} : {', '.join(vides.values())}."
        )


def get_regles(conn: sqlite3.Connection) -> dict:
    """Règles actuelles, pour l'interface : champs de base, attributs, portée."""
    return {
        "champs": champs_requis(conn),
        "attributs": list(attributs_requis(conn)),
        "portee": portee(conn),
        "libelles": CHAMPS,
    }
