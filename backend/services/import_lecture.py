"""Lecture d'un fichier de l'équipe et conversion de ses cellules en valeurs de la base.

Aucune écriture ici : le résultat sert à classer chaque ligne (import_analyse).
"""

import io
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from backend import db
from backend.services import parametres
from backend.services.import_colonnes import (
    ALIAS_ENTETES,
    COLONNES,
    NOM_FEUILLE,
    NOM_FEUILLE_META,
    OBLIGATOIRES,
    normaliser_entete,
)

NATURES: dict[str, str] = {c.champ: c.nature for c in COLONNES} | {"qte_ensemble": "entier"}
LIBELLES: dict[str, str] = {c.champ: c.entete for c in COLONNES} | {
    "qte_ensemble": "Qté dans cet ensemble"
}


class FichierIllisible(Exception):
    """Le fichier n'est pas un classeur exploitable."""


@dataclass
class Classeur:
    """Contenu utile d'un fichier déposé."""

    meta: dict[str, str]
    colonnes: set[str]
    lignes: list[tuple[int, dict[str, Any]]]  # (numéro de ligne Excel, champ -> valeur brute)
    entetes: dict[str, str]  # champ -> en-tête tel qu'écrit dans le fichier


@dataclass
class Contexte:
    """Référentiels de la base utilisés pour convertir les valeurs."""

    blocs: dict[str, str]
    fournisseurs: dict[str, str]
    listes: dict[str, dict[str, str]]
    taux_defaut: float
    bloc_defaut: str | None = None


@dataclass
class LigneLue:
    """Une ligne convertie : valeurs typées, erreurs bloquantes, avertissements."""

    numero: int
    brut: dict[str, str]
    valeurs: dict[str, Any] = field(default_factory=dict)
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def _texte_cellule(valeur: Any) -> str | None:
    """Texte d'une cellule : les nombres entiers perdent leur « .0 », les dates leur heure."""
    if valeur is None:
        return None
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    if isinstance(valeur, datetime):
        valeur = valeur.date().isoformat()
    texte = str(valeur).strip()
    return texte or None


def read_classeur(contenu: bytes) -> Classeur:
    """Lit la feuille des composants et, si présente, la feuille d'identification."""
    try:
        classeur = load_workbook(io.BytesIO(contenu), data_only=True)
    except (BadZipFile, InvalidFileException, KeyError, ValueError, OSError) as erreur:
        raise FichierIllisible(f"Fichier illisible comme classeur Excel ({erreur}).") from erreur
    meta = {}
    if NOM_FEUILLE_META in classeur.sheetnames:
        for cle, valeur, *_ in classeur[NOM_FEUILLE_META].iter_rows(values_only=True):
            if cle:
                meta[str(cle)] = _texte_cellule(valeur) or ""
    feuille = (
        classeur[NOM_FEUILLE] if NOM_FEUILLE in classeur.sheetnames else classeur.worksheets[0]
    )
    lignes = feuille.iter_rows(values_only=True)
    entetes_brutes = next(lignes, ())
    positions, entetes = {}, {}
    for index, entete in enumerate(entetes_brutes):
        champ = ALIAS_ENTETES.get(normaliser_entete(entete)) if entete else None
        if champ and champ not in positions:
            positions[champ] = index
            entetes[champ] = str(entete)
    if "designation" not in positions and "id" not in positions:
        raise FichierIllisible("Aucune colonne « ID » ni « Désignation » : ce n'est pas un modèle.")
    resultat = []
    for numero, ligne in enumerate(lignes, start=2):
        brut = {champ: ligne[i] if i < len(ligne) else None for champ, i in positions.items()}
        resultat.append((numero, brut))
    return Classeur(meta, set(positions), resultat, entetes)


def _cle(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte.lower())
    return re.sub(
        r"\s+", " ", "".join(c for c in decompose if not unicodedata.combining(c))
    ).strip()


def load_contexte(conn: sqlite3.Connection, bloc_defaut: str | None) -> Contexte:
    """Charge blocs, fournisseurs et listes, indexés par code et par libellé normalisés."""
    blocs = {}
    for bloc in db.fetch_all(conn, "SELECT code, nom FROM bloc"):
        blocs[_cle(bloc["code"])] = bloc["code"]
        blocs[_cle(bloc["nom"])] = bloc["code"]
    fournisseurs = {
        _cle(f["nom"]): f["nom"]
        for f in db.fetch_all(conn, "SELECT nom FROM fournisseur WHERE archive = 0")
    }
    listes: dict[str, dict[str, str]] = {}
    for valeur in db.fetch_all(conn, "SELECT liste, code, libelle FROM valeur_liste"):
        index = listes.setdefault(valeur["liste"], {})
        index[_cle(valeur["code"])] = valeur["code"]
        index[_cle(valeur["libelle"])] = valeur["code"]
    return Contexte(blocs, fournisseurs, listes, parametres.get_taux_tva_defaut(conn), bloc_defaut)


def _nombre(texte: str) -> float | None:
    nettoye = re.sub(r"[\s  €%]", "", texte).replace(",", ".")
    try:
        return float(nettoye)
    except ValueError:
        return None


def _convertir(champ: str, valeur: Any, ctx: Contexte) -> tuple[Any, str | None]:
    """Valeur typée d'une cellule, ou message d'erreur en français."""
    texte = _texte_cellule(valeur)
    nature, libelle = NATURES[champ], LIBELLES[champ]
    if texte is None:
        return None, None
    if nature in ("texte", "id"):
        return texte, None
    if nature in ("bloc", "fournisseur", "liste"):
        index = {"bloc": ctx.blocs, "fournisseur": ctx.fournisseurs}.get(nature)
        code = (index if index is not None else ctx.listes.get(champ, {})).get(_cle(texte))
        return (code, None) if code else (None, f"{libelle} : « {texte} » inconnu dans la liste")
    if nature == "base":
        base = texte.upper()
        if base in ("HT", "TTC"):
            return base, None
        return None, f"{libelle} : « {texte} » (HT ou TTC attendu)"
    est_nombre = isinstance(valeur, int | float) and not isinstance(valeur, bool)
    nombre = valeur if est_nombre else _nombre(texte)
    if nombre is None or nombre < 0:
        return None, f"{libelle} : « {texte} » n'est pas un nombre positif"
    if nature == "entier":
        if float(nombre).is_integer():
            return int(nombre), None
        return None, f"{libelle} : « {texte} » n'est pas un nombre entier"
    if nature == "taux":
        taux = nombre / 100 if nombre >= 1 else float(nombre)
        return (taux, None) if taux < 1 else (None, f"{libelle} : « {texte} » invalide")
    return float(nombre), None


def convert_ligne(numero: int, brut: dict[str, Any], ctx: Contexte) -> LigneLue | None:
    """Convertit une ligne ; None si elle est entièrement vide."""
    textes = {champ: _texte_cellule(v) for champ, v in brut.items()}
    if all(v is None for v in textes.values()):
        return None
    lue = LigneLue(numero, {k: v for k, v in textes.items() if v is not None})
    for champ, valeur in brut.items():
        converti, erreur = _convertir(champ, valeur, ctx)
        if erreur:
            lue.erreurs.append(erreur)
        lue.valeurs[champ] = converti
    return lue


def complete_nouveau(lue: LigneLue, ctx: Contexte) -> None:
    """Valeurs par défaut et champs obligatoires d'un composant à créer."""
    valeurs = lue.valeurs
    if valeurs.get("bloc_code") is None and ctx.bloc_defaut:
        valeurs["bloc_code"] = ctx.bloc_defaut
    if valeurs.get("bloc_code") is None and not any("bloc" in e.lower() for e in lue.erreurs):
        lue.erreurs.append("champ obligatoire manquant : Bloc")
    # Dans un modèle d'ensemble, la quantité de l'ensemble tient lieu de besoin.
    if valeurs.get("qte_besoin") is None and valeurs.get("qte_ensemble"):
        valeurs["qte_besoin"] = valeurs["qte_ensemble"]
    for champ, libelle in OBLIGATOIRES.items():
        deja_signale = any(champ in e or libelle in e for e in lue.erreurs)
        if valeurs.get(champ) is None and not deja_signale:
            lue.erreurs.append(f"champ obligatoire manquant : {libelle}")
    valeurs["statut_appro"] = valeurs.get("statut_appro") or "Non lance"
    valeurs["base_prix_releve"] = valeurs.get("base_prix_releve") or "HT"
    if valeurs.get("taux_tva") is None:
        valeurs["taux_tva"] = ctx.taux_defaut
    for champ in ("qte_rechange", "qte_disponible"):
        valeurs[champ] = valeurs.get(champ) or 0
