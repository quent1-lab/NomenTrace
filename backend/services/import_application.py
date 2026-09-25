"""Application des propositions retenues d'un dépôt, en une seule transaction.

Chaque ligne est vérifiée avant d'être écrite : si la base a changé depuis l'analyse sur un
champ concerné, la ligne est refusée et signalée plutôt qu'écrasée. Toute écriture est
journalisée avec l'origine « import » et le lot, donc le fichier, qui l'a produite.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import attributs, composants, import_depots, journal, sauvegardes
from backend.services.import_analyse import avec_attributs, identiques

ORIGINE = journal.ORIGINE_IMPORT


class LigneRefusee(Exception):
    """La ligne ne peut pas être appliquée telle qu'analysée."""


class Application:
    """État d'une application : composants créés par ligne, décompte, refus."""

    def __init__(self, conn: sqlite3.Connection, decisions: dict[str, dict]) -> None:
        self.conn = conn
        self.decisions = decisions
        self.crees: dict[int, str] = {}
        self.appliquees = 0
        self.refus: list[str] = []


# --- Écritures élémentaires -----------------------------------------------------------------


def _composant_actif(conn: sqlite3.Connection, identifiant: str) -> dict:
    composant = db.fetch_one(conn, "SELECT * FROM composant WHERE id = ?", (identifiant,))
    if composant is None:
        raise LigneRefusee(f"{identifiant} n'existe plus.")
    return avec_attributs(conn, [composant])[0]


def _separer(valeurs: dict) -> tuple[dict, dict]:
    """Champs du composant d'un côté, attributs ({code: valeur}) de l'autre."""
    prefixe = attributs.PREFIXE_CHAMP
    champs = {c: v for c, v in valeurs.items() if not c.startswith(prefixe)}
    caracteristiques = {
        c.removeprefix(prefixe): v for c, v in valeurs.items() if c.startswith(prefixe)
    }
    return champs, caracteristiques


def _attribuer(conn: sqlite3.Connection, identifiant: str, valeurs: dict, lot: int) -> None:
    try:
        attributs.set_valeurs(conn, identifiant, valeurs, ORIGINE, lot)
    except ErreurMetier as erreur:
        raise LigneRefusee(erreur.message) from erreur


def _modifier(conn: sqlite3.Connection, identifiant: str, modifs: dict, lot: int) -> None:
    champs, caracteristiques = _separer(modifs)
    journal.update_with_journal(
        conn, "composant", identifiant, champs, composants.CHAMPS_MODIFIABLES, ORIGINE, lot_id=lot
    )
    _attribuer(conn, identifiant, caracteristiques, lot)
    conn.execute(
        "UPDATE composant SET modifie_le = ? WHERE id = ?",
        (datetime.now().isoformat(timespec="seconds"), identifiant),
    )


def _affecter(
    conn: sqlite3.Connection, ensemble: str, identifiant: str, qte: int, lot: int
) -> None:
    """Crée l'affectation, ou augmente sa quantité si elle existe déjà."""
    if not db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ? AND archive = 0", (ensemble,)):
        raise LigneRefusee(f"l'ensemble {ensemble} n'existe plus ou est archivé.")
    existante = db.fetch_one(
        conn,
        "SELECT * FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
        (ensemble, identifiant),
    )
    cle = f"{ensemble}:{identifiant}"
    if existante:
        nouvelle = existante["qte"] + qte
        conn.execute("UPDATE affectation SET qte = ? WHERE id = ?", (nouvelle, existante["id"]))
        journal.write_journal(
            conn, "affectation", cle, "qte", existante["qte"], nouvelle, ORIGINE, lot
        )
    else:
        db.insert_row(
            conn,
            "affectation",
            {"ensemble_code": ensemble, "composant_id": identifiant, "qte": qte},
        )
        journal.write_journal(conn, "affectation", cle, "qte", None, qte, ORIGINE, lot)


def _creer(app: Application, ligne: dict) -> str:
    donnees = ligne["donnees"]
    valeurs, caracteristiques = _separer(
        {k: v for k, v in donnees["valeurs"].items() if v is not None}
    )
    try:
        identifiant = composants.insert_composant(app.conn, valeurs, ORIGINE, ligne["lot_id"])
    except ErreurMetier as erreur:
        raise LigneRefusee(erreur.message) from erreur
    _attribuer(app.conn, identifiant, caracteristiques, ligne["lot_id"])
    if donnees.get("affectation"):
        _affecter(
            app.conn,
            donnees["affectation"]["ensemble"],
            identifiant,
            donnees["affectation"]["qte"],
            ligne["lot_id"],
        )
    app.crees[ligne["id"]] = identifiant
    return identifiant


def _fusionner(app: Application, ligne: dict, identifiant: str, verifier: int | None) -> None:
    """Ajoute le besoin de la ligne au composant existant, et son affectation éventuelle."""
    composant = _composant_actif(app.conn, identifiant)
    if verifier is not None and composant["qte_besoin"] != verifier:
        raise LigneRefusee(f"le besoin de {identifiant} a changé depuis l'analyse.")
    donnees = ligne["donnees"]
    ajout = donnees["valeurs"].get("qte_besoin") or 0
    if ajout:
        _modifier(
            app.conn, identifiant, {"qte_besoin": composant["qte_besoin"] + ajout}, ligne["lot_id"]
        )
    if donnees.get("affectation"):
        _affecter(
            app.conn,
            donnees["affectation"]["ensemble"],
            identifiant,
            donnees["affectation"]["qte"],
            ligne["lot_id"],
        )


# --- Nouvelles entités ---------------------------------------------------------------------


def _creer_entite(conn: sqlite3.Connection, entite: dict, lot: int) -> bool:
    """Crée le fournisseur, la valeur de liste ou l'ensemble ; rien s'il existe déjà."""
    if entite["type"] == "fournisseur":
        if db.fetch_one(conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (entite["nom"],)):
            return False
        # Trouvé par l'équipe : à compléter et valider par une personne autorisée.
        db.insert_row(conn, "fournisseur", {"nom": entite["nom"], "statut": "A valider"})
        journal.write_journal(
            conn, "fournisseur", entite["nom"], "creation", None, "créé", ORIGINE, lot
        )
        return True
    if entite["type"] == "ensemble":
        if db.fetch_one(conn, "SELECT 1 FROM ensemble WHERE code = ?", (entite["code"],)):
            return False
        ordre = conn.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM ensemble").fetchone()[0]
        db.insert_row(
            conn, "ensemble", {"code": entite["code"], "nom": entite["nom"], "ordre": ordre}
        )
        journal.write_journal(
            conn, "ensemble", entite["code"], "creation", None, "créé", ORIGINE, lot
        )
        return True
    cle = (entite["liste"], entite["code"])
    if db.fetch_one(conn, "SELECT 1 FROM valeur_liste WHERE liste = ? AND code = ?", cle):
        return False
    conn.execute(
        "INSERT INTO valeur_liste (liste, code, libelle, ordre)"
        " SELECT ?, ?, ?, COALESCE(MAX(ordre), 0) + 1 FROM valeur_liste WHERE liste = ?",
        (entite["liste"], entite["code"], entite["libelle"], entite["liste"]),
    )
    journal.write_journal(
        conn, "valeur_liste", ":".join(cle), "creation", None, "créée", ORIGINE, lot
    )
    return True


def _appliquer_entite(app: Application, ligne: dict, decision: dict) -> bool:
    if decision.get("action") != "creer":
        return False
    return _creer_entite(app.conn, ligne["donnees"]["entite"], ligne["lot_id"])


# --- Une ligne par catégorie ----------------------------------------------------------------------


def _appliquer_modifie(app: Application, ligne: dict, decision: dict) -> bool:
    champs = [c for c in decision.get("champs", []) if c in ligne["donnees"]["differences"]]
    if not champs:
        return False
    composant = _composant_actif(app.conn, ligne["composant_id"])
    for champ in champs:
        if not identiques(
            champ, composant.get(champ), ligne["donnees"]["differences"][champ]["actuel"]
        ):
            raise LigneRefusee(
                f"{ligne['composant_id']} : « {champ} » a été modifié depuis l'analyse."
            )
    modifs = {c: ligne["donnees"]["differences"][c]["propose"] for c in champs}
    fournisseur = modifs.get("fournisseur_nom")
    if fournisseur and not db.fetch_one(
        app.conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (fournisseur,)
    ):
        raise LigneRefusee(f"le fournisseur « {fournisseur} » n'a pas été créé.")
    _modifier(app.conn, ligne["composant_id"], modifs, ligne["lot_id"])
    return True


def _appliquer_nouveau(app: Application, ligne: dict, decision: dict) -> bool:
    action = decision.get("action", "ignorer")
    if action == "creer":
        _creer(app, ligne)
        return True
    if action != "fusionner":
        return False
    cible = decision.get("cible") or {}
    candidats = ligne["donnees"].get("candidats", [])
    if cible.get("composant"):
        candidat = next((c for c in candidats if c.get("id") == cible["composant"]), None)
        _fusionner(app, ligne, cible["composant"], candidat["qte_besoin"] if candidat else None)
    elif cible.get("ligne"):
        # Fusion avec une autre ligne du dépôt : si elle n'a pas été créée, celle-ci l'est.
        cree = app.crees.get(int(cible["ligne"]))
        if cree:
            _fusionner(app, ligne, cree, None)
        else:
            _creer(app, ligne)
    else:
        raise LigneRefusee("fusion demandée sans composant cible.")
    return True


def _appliquer_affectation(app: Application, ligne: dict, decision: dict) -> bool:
    if decision.get("action") != "appliquer":
        return False
    d = ligne["donnees"]
    existante = db.fetch_one(
        app.conn,
        "SELECT * FROM affectation WHERE ensemble_code = ? AND composant_id = ?",
        (d["ensemble"], ligne["composant_id"]),
    )
    if (existante["qte"] if existante else None) != d["qte_actuelle"]:
        raise LigneRefusee(f"l'affectation de {ligne['composant_id']} à {d['ensemble']} a changé.")
    cle, lot = f"{d['ensemble']}:{ligne['composant_id']}", ligne["lot_id"]
    if ligne["categorie"] == "CREATION_AFFECTATION":
        _affecter(app.conn, d["ensemble"], ligne["composant_id"], d["qte_proposee"], lot)
    elif ligne["categorie"] == "MODIF_AFFECTATION":
        app.conn.execute(
            "UPDATE affectation SET qte = ? WHERE id = ?", (d["qte_proposee"], existante["id"])
        )
        journal.write_journal(
            app.conn, "affectation", cle, "qte", existante["qte"], d["qte_proposee"], ORIGINE, lot
        )
    else:
        app.conn.execute("DELETE FROM affectation WHERE id = ?", (existante["id"],))
        journal.write_journal(
            app.conn, "affectation", cle, "qte", existante["qte"], None, ORIGINE, lot
        )
    return True


APPLICATEURS: dict[str, Any] = {
    "NOUVELLE_ENTITE": _appliquer_entite,
    "MODIFIE": _appliquer_modifie,
    "NOUVEAU": _appliquer_nouveau,
    "DOUBLON": _appliquer_nouveau,
    "CREATION_AFFECTATION": _appliquer_affectation,
    "MODIF_AFFECTATION": _appliquer_affectation,
    "SUPPRESSION_AFFECTATION": _appliquer_affectation,
}


def _appliquer_ligne(app: Application, ligne: dict) -> None:
    applicateur = APPLICATEURS.get(ligne["categorie"])
    decision = app.decisions.get(str(ligne["id"]), {})
    if applicateur is None or not decision:
        return
    app.conn.execute("SAVEPOINT ligne")
    try:
        applique = applicateur(app, ligne, decision)
    except (LigneRefusee, sqlite3.IntegrityError) as refus:
        app.conn.execute("ROLLBACK TO ligne")
        app.conn.execute("RELEASE ligne")
        app.refus.append(f"{ligne['donnees']['fichier']}, ligne {ligne['numero_ligne']} : {refus}")
        return
    app.conn.execute("RELEASE ligne")
    if applique:
        app.appliquees += 1
        app.conn.execute(
            "UPDATE import_ligne SET decision = ?, applique_le = ? WHERE id = ?",
            (
                json.dumps(decision, ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
                ligne["id"],
            ),
        )


def apply_depot(
    conn: sqlite3.Connection,
    chemin_base: Path,
    dossier_sauvegardes: Path,
    depot: int,
    decisions: dict[str, dict],
) -> dict:
    """Applique les décisions ; une sauvegarde de la base est prise juste avant."""
    lots = import_depots.get_lots(conn, depot)
    if lots[0]["statut"] != "analyse":
        raise ErreurMetier(
            f"Le dépôt {depot} est déjà {lots[0]['statut']} : il ne peut plus être appliqué."
        )
    sauvegardes.create_sauvegarde(chemin_base, dossier_sauvegardes)
    app = Application(conn, decisions)
    with db.transaction(conn, immediate=True):
        lignes = import_depots.list_lignes(conn, depot)
        # Les entités d'abord : les lignes qui les citent en ont besoin.
        lignes.sort(key=lambda ligne: ligne["categorie"] != "NOUVELLE_ENTITE")
        for ligne in lignes:
            _appliquer_ligne(app, ligne)
        conn.execute("UPDATE import_lot SET statut = 'applique' WHERE depot = ?", (depot,))
    return {"appliquees": app.appliquees, "refus": app.refus, "crees": list(app.crees.values())}
