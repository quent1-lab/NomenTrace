"""Suppressions physiques, réservées à ce qui n'a laissé aucune trace, et purge du journal.

Tout le reste ne peut qu'être archivé. Chaque suppression prend d'abord une sauvegarde de
la base, s'exécute dans une transaction et laisse une ligne de journal (champ
« suppression », ancienne valeur = résumé JSON de la ligne supprimée).
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import journal, sauvegardes

journal_log = logging.getLogger(__name__)

CHAMP_SUPPRESSION: str = "suppression"
ACTIONS: frozenset[str] = frozenset({"supprimer", "archiver"})


@dataclass(frozen=True)
class Emplacements:
    """Où prendre la sauvegarde préalable et où sont rangés les fichiers joints."""

    chemin_base: Path
    dossier_sauvegardes: Path
    dossier_documents: Path


def _resume(donnees: dict[str, Any]) -> str:
    return json.dumps(donnees, ensure_ascii=False, default=str)


def _pluriel(nombre: int, singulier: str, pluriel: str) -> str:
    return f"{nombre} {singulier if nombre == 1 else pluriel}"


def _sauvegarder(emplacements: Emplacements) -> None:
    """Sauvegarde préalable : une suppression ne part jamais sans elle."""
    if sauvegardes.create_sauvegarde(emplacements.chemin_base, emplacements.dossier_sauvegardes):
        return
    raise ErreurMetier("Sauvegarde préalable impossible : suppression annulée.", 500)


# --- Raisons de refus -----------------------------------------------------------------------


def raison_composant(ligne: dict) -> str | None:
    """Raison qui interdit de supprimer un composant (ligne de v_qualite_composant)."""
    traces = []
    if ligne["nb_lignes_commande"]:
        traces.append(
            _pluriel(ligne["nb_lignes_commande"], "ligne de commande", "lignes de commande")
        )
    if ligne["nb_mouvements"]:
        traces.append(_pluriel(ligne["nb_mouvements"], "mouvement de stock", "mouvements de stock"))
    if ligne["nb_documents"]:
        traces.append(_pluriel(ligne["nb_documents"], "document joint", "documents joints"))
    if ligne["remplace_par"] or ligne["nb_remplaces"]:
        traces.append("lié à un reclassement")
    return ("a laissé des traces : " + ", ".join(traces)) if traces else None


def raison_commande(conn: sqlite3.Connection, numero: str) -> str | None:
    """Raison qui interdit de supprimer une commande : pièces reçues ou mouvements liés."""
    recues = conn.execute(
        "SELECT COUNT(*) FROM ligne_commande WHERE commande_numero = ? AND qte_recue > 0",
        (numero,),
    ).fetchone()[0]
    mouvements = conn.execute(
        "SELECT COUNT(*) FROM mouvement_stock WHERE commande_numero = ?", (numero,)
    ).fetchone()[0]
    traces = []
    if recues:
        traces.append(_pluriel(recues, "ligne reçue", "lignes reçues"))
    if mouvements:
        traces.append(_pluriel(mouvements, "mouvement de stock lié", "mouvements de stock liés"))
    return ("a laissé des traces : " + ", ".join(traces)) if traces else None


def _compter(conn: sqlite3.Connection, sql: str, cle: str) -> int:
    return int(conn.execute(sql, (cle,)).fetchone()[0])


def raison_fournisseur(conn: sqlite3.Connection, nom: str) -> str | None:
    """Un fournisseur ne se supprime que s'il n'est cité nulle part, archivés compris."""
    nb_composants = _compter(conn, "SELECT COUNT(*) FROM composant WHERE fournisseur_nom = ?", nom)
    nb_commandes = _compter(conn, "SELECT COUNT(*) FROM commande WHERE fournisseur_nom = ?", nom)
    cites = []
    if nb_composants:
        cites.append(_pluriel(nb_composants, "composant", "composants"))
    if nb_commandes:
        cites.append(_pluriel(nb_commandes, "commande", "commandes"))
    return ("cité par " + " et ".join(cites) + ", archivés compris") if cites else None


def raison_bloc(conn: sqlite3.Connection, code: str) -> str | None:
    """Un bloc ne se supprime que s'il n'a jamais porté de composant."""
    nombre = _compter(conn, "SELECT COUNT(*) FROM composant WHERE bloc_code = ?", code)
    if nombre:
        return f"porte {_pluriel(nombre, 'composant', 'composants')}, archivés compris"
    return None


def raison_ensemble(conn: sqlite3.Connection, code: str) -> str | None:
    """Un ensemble ne se supprime que sans affectation, sans montage et sans sous-ensemble."""
    affectations = _compter(conn, "SELECT COUNT(*) FROM affectation WHERE ensemble_code = ?", code)
    montages = _compter(conn, "SELECT COUNT(*) FROM mouvement_stock WHERE ensemble_code = ?", code)
    enfants = _compter(conn, "SELECT COUNT(*) FROM ensemble WHERE parent_code = ?", code)
    traces = []
    if affectations:
        traces.append(_pluriel(affectations, "affectation", "affectations"))
    if montages:
        traces.append(_pluriel(montages, "mouvement de montage", "mouvements de montage"))
    if enfants:
        traces.append(_pluriel(enfants, "sous-ensemble", "sous-ensembles"))
    return ("a laissé des traces : " + ", ".join(traces)) if traces else None


# --- Suppressions unitaires (dans une transaction ouverte par l'appelant) ------------------


def _delete_composant(conn: sqlite3.Connection, identifiant: str) -> None:
    """Supprime un composant, ses affectations et ses caractéristiques."""
    ligne = db.fetch_one(conn, "SELECT * FROM composant WHERE id = ?", (identifiant,))
    affectations = db.fetch_all(
        conn, "SELECT ensemble_code, qte FROM affectation WHERE composant_id = ?", (identifiant,)
    )
    caracteristiques = db.fetch_all(
        conn,
        "SELECT attribut_code, valeur_texte, valeur_nombre FROM composant_attribut"
        " WHERE composant_id = ?",
        (identifiant,),
    )
    conn.execute("DELETE FROM affectation WHERE composant_id = ?", (identifiant,))
    conn.execute("DELETE FROM composant_attribut WHERE composant_id = ?", (identifiant,))
    conn.execute("DELETE FROM composant WHERE id = ?", (identifiant,))
    resume = _resume({**(ligne or {}), "affectations": affectations, "attributs": caracteristiques})
    journal.write_journal(conn, "composant", identifiant, CHAMP_SUPPRESSION, resume, None)


def _delete_commande(conn: sqlite3.Connection, numero: str) -> list[str]:
    """Supprime une commande, ses lignes et ses documents ; renvoie les fichiers à effacer."""
    ligne = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero,))
    lignes = db.fetch_all(conn, "SELECT * FROM ligne_commande WHERE commande_numero = ?", (numero,))
    documents = db.fetch_all(
        conn, "SELECT id, nom_origine, chemin FROM document WHERE commande_numero = ?", (numero,)
    )
    conn.execute("DELETE FROM document WHERE commande_numero = ?", (numero,))
    conn.execute("DELETE FROM ligne_commande WHERE commande_numero = ?", (numero,))
    conn.execute("DELETE FROM commande WHERE numero = ?", (numero,))
    resume = _resume({**(ligne or {}), "lignes": lignes, "documents": documents})
    journal.write_journal(conn, "commande", numero, CHAMP_SUPPRESSION, resume, None)
    return [d["chemin"] for d in documents]


def _effacer_fichiers(dossier: Path, chemins: list[str]) -> None:
    """Efface les fichiers des documents supprimés, une fois la transaction validée."""
    racine = dossier.resolve()
    for relatif in chemins:
        fichier = (dossier / relatif).resolve()
        if not fichier.is_relative_to(racine):
            journal_log.warning("Chemin de document hors du dossier ignoré : %s", relatif)
            continue
        try:
            fichier.unlink(missing_ok=True)
            if fichier.parent != racine and not any(fichier.parent.iterdir()):
                fichier.parent.rmdir()
        except OSError as erreur:
            journal_log.warning("Fichier %s non effacé : %s", fichier, erreur)


# --- Traitements en lot ----------------------------------------------------------------------


def _recapitulatif() -> dict[str, list]:
    return {"supprimes": [], "archives": [], "refuses": []}


def _check_action(action: str) -> None:
    if action not in ACTIONS:
        raise ErreurMetier(f"Action inconnue : « {action} ».")


def _trier_composants(conn: sqlite3.Connection, ids: list[str], action: str) -> dict[str, list]:
    recap = _recapitulatif()
    for identifiant in dict.fromkeys(ids):
        ligne = db.fetch_one(conn, "SELECT * FROM v_qualite_composant WHERE id = ?", (identifiant,))
        if ligne is None:
            recap["refuses"].append({"cle": identifiant, "raison": "introuvable"})
        elif action == "archiver" and ligne["archive"]:
            recap["refuses"].append({"cle": identifiant, "raison": "déjà archivé"})
        elif action == "supprimer" and (raison := raison_composant(ligne)):
            recap["refuses"].append({"cle": identifiant, "raison": raison})
        else:
            recap["supprimes" if action == "supprimer" else "archives"].append(identifiant)
    return recap


def process_composants(
    conn: sqlite3.Connection,
    emplacements: Emplacements,
    ids: list[str],
    action: str,
    simuler: bool = False,
) -> dict[str, list]:
    """Supprime ou archive des composants en lot ; `simuler` rend le récapitulatif seul."""
    _check_action(action)
    recap = _trier_composants(conn, ids, action)
    if simuler or not (recap["supprimes"] or recap["archives"]):
        return recap
    if recap["supprimes"]:
        _sauvegarder(emplacements)
    with db.transaction(conn, immediate=True):
        # Relu dans la transaction : rien n'a pu laisser de trace entre-temps.
        recap = _trier_composants(conn, ids, action)
        for identifiant in recap["supprimes"]:
            _delete_composant(conn, identifiant)
        for identifiant in recap["archives"]:
            journal.update_with_journal(
                conn, "composant", identifiant, {"archive": 1}, frozenset({"archive"})
            )
    return recap


def _trier_commandes(conn: sqlite3.Connection, numeros: list[str], action: str) -> dict:
    recap = _recapitulatif()
    for numero in dict.fromkeys(numeros):
        ligne = db.fetch_one(conn, "SELECT archive FROM commande WHERE numero = ?", (numero,))
        if ligne is None:
            recap["refuses"].append({"cle": numero, "raison": "introuvable"})
        elif action == "archiver" and ligne["archive"]:
            recap["refuses"].append({"cle": numero, "raison": "déjà archivée"})
        elif action == "supprimer" and (raison := raison_commande(conn, numero)):
            recap["refuses"].append({"cle": numero, "raison": raison})
        else:
            recap["supprimes" if action == "supprimer" else "archives"].append(numero)
    return recap


def process_commandes(
    conn: sqlite3.Connection,
    emplacements: Emplacements,
    numeros: list[str],
    action: str,
    simuler: bool = False,
) -> dict[str, list]:
    """Supprime (lignes et documents compris) ou archive des commandes en lot."""
    _check_action(action)
    recap = _trier_commandes(conn, numeros, action)
    if simuler or not (recap["supprimes"] or recap["archives"]):
        return recap
    if recap["supprimes"]:
        _sauvegarder(emplacements)
    fichiers: list[str] = []
    with db.transaction(conn, immediate=True):
        recap = _trier_commandes(conn, numeros, action)
        for numero in recap["supprimes"]:
            fichiers.extend(_delete_commande(conn, numero))
        for numero in recap["archives"]:
            journal.update_with_journal(
                conn, "commande", numero, {"archive": 1}, frozenset({"archive"})
            )
    _effacer_fichiers(emplacements.dossier_documents, fichiers)
    return recap


# --- Blocs, ensembles, fournisseurs ------------------------------------------------------------


@dataclass(frozen=True)
class Entite:
    """Entité supprimable : requêtes écrites en entier, libellé et contrôle des traces."""

    table: str
    lecture: str
    suppression: str
    libelle: str


ENTITES: dict[str, Entite] = {
    "bloc": Entite(
        "bloc", "SELECT * FROM bloc WHERE code = ?", "DELETE FROM bloc WHERE code = ?", "Bloc"
    ),
    "ensemble": Entite(
        "ensemble",
        "SELECT * FROM ensemble WHERE code = ?",
        "DELETE FROM ensemble WHERE code = ?",
        "Ensemble",
    ),
    "fournisseur": Entite(
        "fournisseur",
        "SELECT * FROM fournisseur WHERE nom = ?",
        "DELETE FROM fournisseur WHERE nom = ?",
        "Fournisseur",
    ),
}
RAISONS = {"bloc": raison_bloc, "ensemble": raison_ensemble, "fournisseur": raison_fournisseur}


def delete_entite(
    conn: sqlite3.Connection, emplacements: Emplacements, type_entite: str, cle: str
) -> None:
    """Supprime un bloc, un ensemble ou un fournisseur qui n'a laissé aucune trace."""
    if type_entite not in ENTITES:
        raise Introuvable(f"Type « {type_entite} » inconnu.")
    entite = ENTITES[type_entite]
    if db.fetch_one(conn, entite.lecture, (cle,)) is None:
        raise Introuvable(f"{entite.libelle} « {cle} » introuvable.")
    if raison := RAISONS[type_entite](conn, cle):
        raise Conflit(f"{entite.libelle} « {cle} » non supprimable : {raison}. Archivez-le.")
    _sauvegarder(emplacements)
    with db.transaction(conn, immediate=True):
        ligne = db.fetch_one(conn, entite.lecture, (cle,))
        if ligne is None:
            raise Introuvable(f"{entite.libelle} « {cle} » introuvable.")
        if raison := RAISONS[type_entite](conn, cle):
            raise Conflit(f"{entite.libelle} « {cle} » non supprimable : {raison}.")
        conn.execute(entite.suppression, (cle,))
        journal.write_journal(conn, entite.table, cle, CHAMP_SUPPRESSION, _resume(ligne), None)


def list_entites_supprimables(conn: sqlite3.Connection) -> list[dict]:
    """Blocs, ensembles et fournisseurs, archivés compris, qui peuvent être supprimés."""
    candidats = [
        ("bloc", r["code"], r["nom"], r["archive"])
        for r in db.fetch_all(conn, "SELECT code, nom, archive FROM bloc ORDER BY ordre, code")
    ]
    candidats += [
        ("ensemble", r["code"], r["nom"], r["archive"])
        for r in db.fetch_all(conn, "SELECT code, nom, archive FROM ensemble ORDER BY ordre, code")
    ]
    candidats += [
        ("fournisseur", r["nom"], r["nom"], r["archive"])
        for r in db.fetch_all(
            conn, "SELECT nom, archive FROM fournisseur ORDER BY nom COLLATE NOCASE"
        )
    ]
    return [
        {"type": type_entite, "cle": cle, "nom": nom, "archive": archive}
        for type_entite, cle, nom, archive in candidats
        if RAISONS[type_entite](conn, cle) is None
    ]


# --- Journal ---------------------------------------------------------------------------------


def purge_journal(conn: sqlite3.Connection, emplacements: Emplacements) -> int:
    """Vide le journal après sauvegarde ; il repart avec une ligne qui trace la purge."""
    _sauvegarder(emplacements)
    with db.transaction(conn, immediate=True):
        nombre = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        conn.execute("DELETE FROM journal")
        journal.write_journal(
            conn, "journal", None, "purge", f"{nombre} ligne(s) supprimée(s)", None
        )
    journal_log.warning("Journal vidé : %d ligne(s) supprimée(s)", nombre)
    return int(nombre)
