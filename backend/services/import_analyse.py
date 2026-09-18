"""Analyse d'un dépôt de fichiers : chaque ligne devient une proposition classée.

Rien n'est modifié dans les données : seules les tables import_lot et import_ligne sont
écrites. L'application des propositions retenues est faite par import_application.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend import db
from backend.services import composants, import_doublons, import_lecture
from backend.services.documents import nom_sur
from backend.services.import_colonnes import CHAMPS_COMPOSANT, COLONNES

TOLERANCE_MONTANT = 0.005  # au centime près
TOLERANCE_TAUX = 1e-6
ENTETES: dict[str, str] = {c.champ: c.entete for c in COLONNES} | {
    "qte_ensemble": "Qté dans cet ensemble"
}
# Champs obligatoires d'un composant existant : une cellule vidée n'est pas une modification.
NON_VIDABLES: tuple[str, ...] = (
    "fonction",
    "designation",
    "mode_appro",
    "qte_besoin",
    "statut_appro",
    "base_prix_releve",
    "taux_tva",
)


@dataclass
class EtatDepot:
    """Ce que l'analyse partage entre les fichiers d'un même dépôt."""

    existants: list[import_doublons.Empreinte]
    par_id: dict[str, dict]
    affectations: dict[tuple[str, str], dict]
    a_creer: list[import_doublons.Empreinte] = field(default_factory=list)
    prochains: dict[str, tuple[str, int]] = field(default_factory=dict)


@dataclass
class Fichier:
    """Le fichier en cours d'analyse et son contexte de conversion."""

    lot_id: int
    nom: str
    colonnes: set[str]
    ctx: import_lecture.Contexte
    ensemble: str | None


def _charger_etat(conn: sqlite3.Connection) -> EtatDepot:
    actifs = db.fetch_all(conn, "SELECT * FROM v_composant")
    return EtatDepot(
        existants=[import_doublons.empreinte(c["id"], c) for c in actifs],
        par_id={c["id"]: c for c in db.fetch_all(conn, "SELECT * FROM composant")},
        affectations={
            (a["ensemble_code"], a["composant_id"]): a
            for a in db.fetch_all(
                conn, "SELECT id, ensemble_code, composant_id, qte FROM affectation"
            )
        },
    )


def identiques(champ: str, actuel: Any, propose: Any) -> bool:
    if actuel is None or propose is None:
        return actuel is None and propose is None
    if champ == "pu_releve":
        return abs(float(actuel) - float(propose)) < TOLERANCE_MONTANT
    if champ == "taux_tva":
        return abs(float(actuel) - float(propose)) < TOLERANCE_TAUX
    if isinstance(actuel, str) or isinstance(propose, str):
        return str(actuel).strip() == str(propose).strip()
    return actuel == propose


def _inserer(
    conn: sqlite3.Connection,
    fichier: Fichier,
    numero: int,
    categorie: str,
    composant_id: str | None,
    donnees: dict,
    score: float | None = None,
) -> int:
    return db.insert_row(
        conn,
        "import_ligne",
        {
            "lot_id": fichier.lot_id,
            "numero_ligne": numero,
            "categorie": categorie,
            "composant_id": composant_id,
            "donnees_json": json.dumps({"fichier": fichier.nom, **donnees}, ensure_ascii=False),
            "score": score,
        },
    )


def _brut(lue: import_lecture.LigneLue) -> dict[str, str]:
    return {ENTETES.get(champ, champ): valeur for champ, valeur in lue.brut.items()}


# --- Lignes avec identifiant ------------------------------------------------------------------


def _differences(lue: import_lecture.LigneLue, fichier: Fichier, composant: dict) -> dict:
    differences = {}
    for champ in CHAMPS_COMPOSANT:
        if champ not in fichier.colonnes:
            continue
        propose = lue.valeurs.get(champ)
        if propose is None and champ in ("qte_rechange", "qte_disponible"):
            propose = 0
        if propose is None and champ in NON_VIDABLES:
            lue.erreurs.append(f"champ obligatoire vidé : {ENTETES[champ]}")
            continue
        if not identiques(champ, composant[champ], propose):
            differences[champ] = {"actuel": composant[champ], "propose": propose}
    return differences


def _seulement_affectation(lue: import_lecture.LigneLue) -> bool:
    """Ligne d'un modèle d'ensemble réduite à l'ID et à la quantité de l'ensemble."""
    return all(lue.valeurs.get(c) is None for c in CHAMPS_COMPOSANT)


def _affectations(
    conn: sqlite3.Connection,
    etat: EtatDepot,
    fichier: Fichier,
    numero: int,
    composant_id: str,
    qte: int | None,
) -> None:
    """Proposition de création, modification ou suppression d'affectation."""
    existante = etat.affectations.get((fichier.ensemble, composant_id))
    if qte:
        if existante is None:
            categorie = "CREATION_AFFECTATION"
        elif existante["qte"] != qte:
            categorie = "MODIF_AFFECTATION"
        else:
            return
    elif existante is not None:
        categorie = "SUPPRESSION_AFFECTATION"
    else:
        return
    donnees = {
        "ensemble": fichier.ensemble,
        "affectation_id": existante["id"] if existante else None,
        "qte_actuelle": existante["qte"] if existante else None,
        "qte_proposee": qte or None,
    }
    _inserer(conn, fichier, numero, categorie, composant_id, donnees)


def _analyse_avec_id(
    conn: sqlite3.Connection, etat: EtatDepot, fichier: Fichier, lue: import_lecture.LigneLue
) -> None:
    identifiant = lue.valeurs["id"]
    composant = etat.par_id.get(identifiant)
    base = {"brut": _brut(lue), "avertissements": lue.avertissements}
    if composant is None:
        raisons = ["identifiant absent de la base", *lue.erreurs]
        _inserer(conn, fichier, lue.numero, "INCONNU", identifiant, {**base, "raisons": raisons})
        return
    seule = fichier.ensemble is not None and _seulement_affectation(lue)
    differences = {} if seule else _differences(lue, fichier, composant)
    if lue.erreurs:
        _inserer(
            conn, fichier, lue.numero, "INVALIDE", identifiant, {**base, "raisons": lue.erreurs}
        )
        return
    bloc = lue.valeurs.get("bloc_code")
    if bloc and bloc != composant["bloc_code"]:
        lue.avertissements.append(
            f"bloc {bloc} indiqué, mais {identifiant} appartient au bloc "
            f"{composant['bloc_code']} : "
            "le bloc est figé dans l'identifiant et n'est pas modifié."
        )
    if composant["archive"]:
        lue.avertissements.append(f"{identifiant} est archivé.")
    categorie = "MODIFIE" if differences else "IDENTIQUE"
    donnees = {**base, "designation": composant["designation"], "differences": differences}
    _inserer(conn, fichier, lue.numero, categorie, identifiant, donnees)
    if fichier.ensemble and "qte_ensemble" in fichier.colonnes and not composant["archive"]:
        _affectations(conn, etat, fichier, lue.numero, identifiant, lue.valeurs.get("qte_ensemble"))


# --- Lignes sans identifiant ------------------------------------------------------------------


def _id_indicatif(conn: sqlite3.Connection, etat: EtatDepot, bloc: str) -> str:
    """Identifiant qu'aurait la ligne si elle était créée : indicatif, attribué à l'application."""
    if bloc not in etat.prochains:
        suivant = composants.next_id(conn, bloc)
        coupure = suivant.rfind("-") + 1
        etat.prochains[bloc] = (suivant[:coupure], int(suivant[coupure:]))
    racine, numero = etat.prochains[bloc]
    etat.prochains[bloc] = (racine, numero + 1)
    return f"{racine}{numero:03d}"


def _candidats(etat: EtatDepot, empreinte: import_doublons.Empreinte) -> list[dict]:
    """Candidats de la base, puis des lignes à créer du même dépôt, les plus sûrs d'abord."""
    candidats = []
    for trouve in import_doublons.search(empreinte, etat.existants):
        c = etat.par_id[trouve["cle"]]
        candidats.append(
            {
                **trouve,
                "type": "composant",
                "id": c["id"],
                "designation": c["designation"],
                "fonction": c["fonction"],
                "ref_fabricant": c["ref_fabricant"],
                "bloc_code": c["bloc_code"],
                "qte_besoin": c["qte_besoin"],
            }
        )
    for trouve in import_doublons.search(empreinte, etat.a_creer):
        if trouve["fusion"]:
            ligne_id, description = trouve["cle"]
            candidats.append({**trouve, "type": "ligne", "ligne_id": ligne_id, **description})
    candidats.sort(key=lambda c: (-c["fusion"], c["type"] == "ligne", c["niveau"], -c["score"]))
    return candidats[: import_doublons.NB_CANDIDATS]


def _analyse_sans_id(
    conn: sqlite3.Connection, etat: EtatDepot, fichier: Fichier, lue: import_lecture.LigneLue
) -> None:
    import_lecture.complete_nouveau(lue, fichier.ctx)
    base = {"brut": _brut(lue), "avertissements": lue.avertissements}
    if lue.erreurs:
        _inserer(conn, fichier, lue.numero, "INVALIDE", None, {**base, "raisons": lue.erreurs})
        return
    valeurs = {c: lue.valeurs.get(c) for c in ("bloc_code", *CHAMPS_COMPOSANT)}
    empreinte = import_doublons.empreinte(None, valeurs)
    candidats = _candidats(etat, empreinte)
    fusion = next((c for c in candidats if c["fusion"]), None)
    affectation = None
    if fichier.ensemble and lue.valeurs.get("qte_ensemble"):
        affectation = {"ensemble": fichier.ensemble, "qte": lue.valeurs["qte_ensemble"]}
    donnees = {
        **base,
        "valeurs": valeurs,
        "affectation": affectation,
        "candidats": candidats,
        "action_defaut": "fusionner" if fusion else "creer",
        "id_indicatif": _id_indicatif(conn, etat, valeurs["bloc_code"]),
    }
    categorie = "DOUBLON" if candidats else "NOUVEAU"
    score = candidats[0]["score"] if candidats else None
    ligne_id = _inserer(conn, fichier, lue.numero, categorie, None, donnees, score)
    if not fusion:
        description = {
            "fichier": fichier.nom,
            "numero": lue.numero,
            "designation": valeurs["designation"],
        }
        empreinte.cle = (ligne_id, description)
        etat.a_creer.append(empreinte)


# --- Dépôt ---------------------------------------------------------------------------------


def _meta(
    conn: sqlite3.Connection, classeur: import_lecture.Classeur
) -> tuple[str | None, str | None, list[str]]:
    """Bloc ou ensemble désigné par la feuille d'identification du modèle."""
    avertissements = []
    type_modele, code = classeur.meta.get("type"), classeur.meta.get("code")
    if type_modele == "bloc" and db.fetch_one(conn, "SELECT 1 FROM bloc WHERE code = ?", (code,)):
        return code, None, avertissements
    if type_modele == "ensemble":
        if db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ? AND archive = 0", (code,)):
            return None, code, avertissements
        avertissements.append(f"ensemble « {code} » introuvable ou archivé : quantités ignorées")
    return None, None, avertissements


def _copier(dossier: Path, nom: str, contenu: bytes) -> str:
    dossier.mkdir(parents=True, exist_ok=True)
    copie = f"{datetime.now():%Y%m%d_%H%M%S}_{nom_sur(nom)}"
    (dossier / copie).write_bytes(contenu)
    return copie


def _analyse_fichier(
    conn: sqlite3.Connection,
    etat: EtatDepot,
    depot: int | None,
    nom: str,
    contenu: bytes,
    meta_lot: dict,
) -> int:
    """Crée le lot du fichier et une proposition par ligne utile ; renvoie l'id du lot."""
    try:
        classeur = import_lecture.read_classeur(contenu)
        bloc, ensemble, avertissements = _meta(conn, classeur)
    except import_lecture.FichierIllisible as erreur:
        classeur, bloc, ensemble, avertissements = None, None, None, [str(erreur)]
    lot_id = db.insert_row(
        conn,
        "import_lot",
        {
            **meta_lot,
            "depot": depot or 0,
            "nom_fichier": nom,
            "bloc_devine": bloc,
            "ensemble_devine": ensemble,
        },
    )
    if depot is None:
        conn.execute("UPDATE import_lot SET depot = id WHERE id = ?", (lot_id,))
    ctx = import_lecture.load_contexte(conn, bloc)
    fichier = Fichier(lot_id, nom, classeur.colonnes if classeur else set(), ctx, ensemble)
    if classeur is None:
        _inserer(conn, fichier, 0, "INVALIDE", None, {"brut": {}, "raisons": avertissements})
        return lot_id
    for numero, brut in classeur.lignes:
        lue = import_lecture.convert_ligne(numero, brut, ctx)
        if lue is None:
            continue
        lue.avertissements.extend(avertissements)
        if lue.valeurs.get("id"):
            _analyse_avec_id(conn, etat, fichier, lue)
        else:
            _analyse_sans_id(conn, etat, fichier, lue)
    return lot_id


def analyse_depot(
    conn: sqlite3.Connection,
    dossier_imports: Path,
    fichiers: list[tuple[str, bytes]],
    depose_par: str | None,
) -> int:
    """Analyse un ou plusieurs fichiers en un dépôt ; renvoie le numéro du dépôt."""
    depot = None
    with db.transaction(conn, immediate=True):
        etat = _charger_etat(conn)
        for nom, contenu in fichiers:
            meta_lot = {
                "depose_par": depose_par,
                "fichier_copie": _copier(dossier_imports, nom, contenu),
            }
            lot_id = _analyse_fichier(conn, etat, depot, nom, contenu, meta_lot)
            depot = depot or lot_id
    return depot
