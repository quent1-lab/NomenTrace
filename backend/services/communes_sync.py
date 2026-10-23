"""Commandes communes : parts de chaque projet et synchronisation des copies (phase 16).

L'en-tête et les frais d'une commune vivent dans la référence du dossier ; ses lignes, dans
la copie de chaque projet présent (seule copie de ces lignes). Tout le reste de la copie se
déduit : en-tête recopié, statut, part des frais (à parts égales entre les projets qui ont
au moins une ligne non annulée), part du montant réel (au prorata de l'estimé de chaque
projet). La synchronisation recalcule tout depuis l'état et le réécrit.

Ordre des écritures (règle de la version) : toute écriture sur une commune augmente d'abord
sa version dans la référence, puis écrit dans le projet, puis synchronise. Une
synchronisation lit la version, lit les lignes, et n'écrit une copie que si la version de
la référence n'a pas bougé entre-temps et n'est pas plus ancienne que celle de la copie.
Une écriture interrompue laisse des copies de version inférieure, rattrapées à l'ouverture
de la commune et au démarrage. Un participant hors ligne arrête la synchronisation avant
toute écriture.
"""

import logging
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import Conflit
from backend.services import journal
from backend.services.commandes import STATUTS_ENGAGES, next_numero

journal_log = logging.getLogger(__name__)

MOTIF_NUMERO = re.compile(r"^CC-(\d+)$")
# Champs de l'en-tête recopiés tels quels dans chaque copie.
CHAMPS_COPIES: tuple[str, ...] = (
    "type",
    "fournisseur_nom",
    "demande_par",
    "date_demande",
    "date_reception_devis",
    "date_commande",
    "livraison_annoncee",
    "taux_tva",
    "reference_externe",
    "lien_document",
    "commentaire",
    "date_transmission_suivi",
    "date_commande_confirmee",
    "livraison_confirmee",
    "date_reception_annoncee",
    "commentaire_suivi",
    "archive",
)
COLONNES_COPIE: frozenset[str] = frozenset({*CHAMPS_COPIES, "statut", "version_commune"})


@dataclass
class Emplacements:
    """Bases d'un dossier utiles à ses communes : référence, liste de l'organisme, projets."""

    dossier: str
    reference: Path
    organisme: Path | None
    projets: dict[str, Path]  # projets du dossier en ligne
    hors_ligne: set[str] = field(default_factory=set)


# --- Calculs (purs) ----------------------------------------------------------------------------


def est_engagee(type_commande: str, statut: str) -> bool:
    return type_commande == "Commande" and statut in STATUTS_ENGAGES


def actives(lignes: list[dict]) -> list[dict]:
    return [ligne for ligne in lignes if ligne["statut_ligne"] != "Annulee"]


def montant_lignes(lignes: list[dict]) -> float:
    """Lignes non annulées ; une ligne sans prix compte 0 (signalé par l'écran)."""
    return sum(ligne["qte_commandee"] * (ligne["pu_ht_devis"] or 0) for ligne in actives(lignes))


def statut_deduit(type_commande: str, statut: str, lignes: list[dict]) -> str:
    """Une fois la commande passée, le statut suit les réceptions des lignes non annulées."""
    if not est_engagee(type_commande, statut):
        return statut
    restantes = actives(lignes)
    if restantes and all(ligne["qte_recue"] >= ligne["qte_commandee"] for ligne in restantes):
        return "Livre"
    if any(ligne["qte_recue"] > 0 for ligne in restantes):
        return "Livre partiel"
    return "Commande"


def repartir(
    lignes: dict[str, list[dict]], frais: list[dict], reel: float | None
) -> dict[str, dict[str, Any]]:
    """Part de chaque projet : frais, estimé et montant réel, en pleine précision.

    Les frais se partagent à parts égales entre les projets présents (au moins une ligne non
    annulée). Le réel se répartit au prorata de l'estimé ; estimé total nul : parts égales
    entre les présents. La somme des parts du réel vaut le réel (le dernier présent prend le
    reste).
    """
    projets = sorted(lignes)
    presents = [p for p in projets if actives(lignes[p])]
    n = len(presents)
    parts: dict[str, dict[str, Any]] = {}
    for projet in projets:
        present = projet in presents
        part_frais = [{**f, "montant_ht": f["montant_ht"] / n if present else 0.0} for f in frais]
        estime = montant_lignes(lignes[projet]) + sum(f["montant_ht"] for f in part_frais)
        parts[projet] = {
            "present": present,
            "lignes_ht": montant_lignes(lignes[projet]),
            "frais": part_frais if present else [],
            "frais_ht": sum(f["montant_ht"] for f in part_frais),
            "estime_ht": estime,
            "reel_ht": None,
            "sans_prix": sum(
                1 for ligne in actives(lignes[projet]) if ligne["pu_ht_devis"] is None
            ),
        }
    if reel is None or not presents:
        return parts
    total = sum(parts[p]["estime_ht"] for p in presents)
    reparti = 0.0
    for rang, projet in enumerate(presents):
        if rang == n - 1:
            part = reel - reparti
        elif total > 0:
            part = reel * parts[projet]["estime_ht"] / total
        else:
            part = reel / n
        parts[projet]["reel_ht"] = part
        reparti += part
    for projet in projets:
        if not parts[projet]["present"]:
            parts[projet]["reel_ht"] = 0.0
    return parts


# --- Lecture et écriture dans les bases ---------------------------------------------------------


@contextmanager
def ouverte(conn: sqlite3.Connection) -> Iterator[None]:
    """Transaction où les copies d'une commune peuvent être écrites (verrou levé)."""
    with db.transaction(conn):
        conn.execute("UPDATE commune_ecriture SET ouverte = 1 WHERE id = 1")
        yield
        conn.execute("UPDATE commune_ecriture SET ouverte = 0 WHERE id = 1")


def lire_commune(ref: sqlite3.Connection, numero: str) -> dict | None:
    return db.fetch_one(ref, "SELECT * FROM commune WHERE numero = ?", (numero,))


def lire_participants(ref: sqlite3.Connection, numero: str) -> dict[str, str]:
    """Projet → numéro local de sa copie."""
    lignes = ref.execute(
        "SELECT projet, numero_local FROM commune_projet WHERE numero = ? ORDER BY projet",
        (numero,),
    ).fetchall()
    return {ligne["projet"]: ligne["numero_local"] for ligne in lignes}


def lire_frais(ref: sqlite3.Connection, numero: str) -> list[dict]:
    return db.fetch_all(
        ref,
        "SELECT f.id, f.type_frais, f.montant_ht, f.commentaire, v.libelle AS type_libelle"
        " FROM frais_commune f LEFT JOIN valeur_liste v"
        " ON v.liste = 'type_frais' AND v.code = f.type_frais"
        " WHERE f.numero = ? ORDER BY f.id",
        (numero,),
    )


def lire_lignes(conn: sqlite3.Connection, numero_local: str) -> list[dict]:
    return db.fetch_all(
        conn,
        "SELECT l.id, l.composant_id, l.qte_commandee, l.pu_ht_devis, l.qte_recue,"
        " l.date_reception, l.statut_ligne, l.commentaire, c.designation, c.pu_ht AS pu_ht_estime"
        " FROM ligne_commande l LEFT JOIN v_composant c ON c.id = l.composant_id"
        " WHERE l.commande_numero = ? ORDER BY l.id",
        (numero_local,),
    )


def augmenter_version(ref: sqlite3.Connection, numero: str) -> int:
    """À faire avant toute écriture sur la commune ou ses lignes (règle de la version)."""
    with db.transaction(ref):
        ref.execute("UPDATE commune SET version = version + 1 WHERE numero = ?", (numero,))
        return ref.execute("SELECT version FROM commune WHERE numero = ?", (numero,)).fetchone()[0]


def assurer_copie(conn: sqlite3.Connection, commune: dict, numero_local: str) -> None:
    """Crée la copie d'un projet si elle manque (dans une transaction `ouverte`).

    Un numéro pris par une commande ordinaire du projet est refusé : les lignes de la
    commune n'entrent jamais dans une autre commande.
    """
    existante = db.fetch_one(conn, "SELECT commune FROM commande WHERE numero = ?", (numero_local,))
    if existante is not None:
        if existante["commune"] != commune["numero"]:
            raise Conflit(
                f"Le numéro {numero_local} de ce projet est pris par une autre commande :"
                f" la copie de {commune['numero']} ne peut pas y être écrite."
            )
        return
    if not db.fetch_one(
        conn, "SELECT 1 FROM fournisseur WHERE nom = ?", (commune["fournisseur_nom"],)
    ):
        raise Conflit(
            f"Le fournisseur « {commune['fournisseur_nom']} » n'est pas dans la liste de ce"
            " projet : vérifier la liste des fournisseurs de l'organisme."
        )
    db.insert_row(
        conn,
        "commande",
        {
            "numero": numero_local,
            "commune": commune["numero"],
            "version_commune": 0,
            "statut": commune["statut"],
            **{champ: commune[champ] for champ in CHAMPS_COPIES},
        },
    )
    journal.write_journal(conn, "commande", numero_local, "creation", None, commune["numero"])


def creer_copie(base: Path, auteur: str | None, commune: dict) -> str:
    """Copie d'un projet qui rejoint la commune, ou celle qu'il a déjà (inscription
    interrompue) ; son numéro est tiré dans la transaction qui la crée."""
    conn = db.connect(base, auteur, creer=False)
    try:
        with ouverte(conn):
            deja = conn.execute(
                "SELECT numero FROM commande WHERE commune = ?", (commune["numero"],)
            ).fetchone()
            if deja is not None:
                return deja[0]
            numero_local = next_numero(conn)
            assurer_copie(conn, commune, numero_local)
            return numero_local
    finally:
        conn.close()


def _fournisseur_a_jour(emp: Emplacements, ref: sqlite3.Connection, commune: dict) -> dict:
    """Suit les renommages de la liste de l'organisme (les copies suivent par cascade)."""
    if emp.organisme is None:
        return commune
    org = db.connect(emp.organisme, creer=False)
    try:
        nom = commune["fournisseur_nom"]
        for ancien, nouveau in org.execute(
            "SELECT ancien, nouveau FROM renommage_fournisseur ORDER BY rang"
        ).fetchall():
            if ancien == nom:
                nom = nouveau
    finally:
        org.close()
    if nom == commune["fournisseur_nom"]:
        return commune
    with db.transaction(ref):
        ref.execute(
            "UPDATE commune SET fournisseur_nom = ? WHERE numero = ?", (nom, commune["numero"])
        )
    journal_log.info("Commune %s : fournisseur renommé en %s", commune["numero"], nom)
    return {**commune, "fournisseur_nom": nom}


def _ecrire_frais(conn: sqlite3.Connection, numero_local: str, voulus: list[dict]) -> None:
    actuels = db.fetch_all(
        conn,
        "SELECT type_frais, montant_ht, commentaire FROM frais_commande"
        " WHERE commande_numero = ? ORDER BY id",
        (numero_local,),
    )
    cibles = [
        {
            "type_frais": f["type_frais"],
            "montant_ht": f["montant_ht"],
            "commentaire": f["commentaire"],
        }
        for f in voulus
    ]
    if len(actuels) == len(cibles) and not any(
        a["type_frais"] != c["type_frais"]
        or a["commentaire"] != c["commentaire"]
        or journal.differe(a["montant_ht"], c["montant_ht"])
        for a, c in zip(actuels, cibles, strict=True)
    ):
        return
    conn.execute("DELETE FROM frais_commande WHERE commande_numero = ?", (numero_local,))
    for frais in cibles:
        db.insert_row(conn, "frais_commande", {"commande_numero": numero_local, **frais})
    journal.write_journal(
        conn,
        "commande",
        numero_local,
        "frais de la commune",
        sum(a["montant_ht"] for a in actuels),
        sum(c["montant_ht"] for c in cibles),
    )


def _ecrire_copie(
    conn: sqlite3.Connection, commune: dict, numero_local: str, part: dict, lignes: list[dict]
) -> bool:
    """Accorde une copie à la commune ; False si la copie a déjà une version plus récente."""
    with ouverte(conn):
        assurer_copie(conn, commune, numero_local)
        copie = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero_local,))
        if (copie["version_commune"] or 0) > commune["version"]:
            return False
        engagee = est_engagee(commune["type"], commune["statut"])
        if engagee:
            for ligne in lignes:
                if ligne["statut_ligne"] == "A commander":
                    journal.update_with_journal(
                        conn,
                        "ligne_commande",
                        ligne["id"],
                        {"statut_ligne": "Commandee"},
                        frozenset({"statut_ligne"}),
                    )
        voulu = {champ: commune[champ] for champ in CHAMPS_COPIES}
        voulu["statut"] = statut_deduit(commune["type"], commune["statut"], lignes)
        voulu["version_commune"] = commune["version"]
        journal.update_with_journal(conn, "commande", numero_local, voulu, COLONNES_COPIE)
        # La part du réel s'écrit au bit près : la somme des parts doit valoir le réel.
        if copie["montant_commande_ht"] != part["reel_ht"]:
            conn.execute(
                "UPDATE commande SET montant_commande_ht = ? WHERE numero = ?",
                (part["reel_ht"], numero_local),
            )
            journal.write_journal(
                conn,
                "commande",
                numero_local,
                "montant_commande_ht",
                copie["montant_commande_ht"],
                part["reel_ht"],
            )
        _ecrire_frais(conn, numero_local, part["frais"])
    return True


def synchroniser(emp: Emplacements, numero: str, auteur: str | None = None) -> dict[str, Any]:
    """Recalcule les parts et accorde chaque copie ; rapport : écrites, manquants, périmée."""
    signature = auteur or f"commande commune {numero}"
    ref = db.connect(emp.reference, signature, creer=False)
    try:
        commune = lire_commune(ref, numero)
        if commune is None:
            return {"ecrites": [], "manquants": [], "perimee": False}
        commune = _fournisseur_a_jour(emp, ref, commune)
        participants = lire_participants(ref, numero)
        manquants = sorted(p for p in participants if p not in emp.projets)
        if manquants:
            journal_log.warning(
                "Commune %s non synchronisée : projets hors ligne %s", numero, manquants
            )
            return {"ecrites": [], "manquants": manquants, "perimee": False}
        lignes = {p: lignes_du_projet(emp.projets[p], n) for p, n in participants.items()}
        parts = repartir(lignes, lire_frais(ref, numero), commune["montant_commande_ht"])
        ecrites = []
        for projet, numero_local in participants.items():
            if _version(ref, numero) != commune["version"]:
                return {"ecrites": ecrites, "manquants": [], "perimee": True}
            conn = db.connect(emp.projets[projet], signature, creer=False)
            try:
                if _ecrire_copie(conn, commune, numero_local, parts[projet], lignes[projet]):
                    ecrites.append(projet)
            finally:
                conn.close()
        toutes = [ligne for lp in lignes.values() for ligne in lp]
        with db.transaction(ref):
            ref.execute(
                "UPDATE commune SET statut_deduit = ?, estime_ht = ? WHERE numero = ?"
                " AND version = ?",
                (
                    statut_deduit(commune["type"], commune["statut"], toutes),
                    sum(p["estime_ht"] for p in parts.values())
                    + (0.0 if parts else sum(f["montant_ht"] for f in lire_frais(ref, numero))),
                    numero,
                    commune["version"],
                ),
            )
    finally:
        ref.close()
    return {"ecrites": ecrites, "manquants": [], "perimee": False}


def _version(ref: sqlite3.Connection, numero: str) -> int:
    return ref.execute("SELECT version FROM commune WHERE numero = ?", (numero,)).fetchone()[0]


def lignes_du_projet(base: Path, numero_local: str) -> list[dict]:
    conn = db.connect(base, creer=False)
    try:
        return lire_lignes(conn, numero_local)
    finally:
        conn.close()


def en_retard(emp: Emplacements) -> list[str]:
    """Communes dont une copie a une version inférieure (écriture interrompue)."""
    ref = db.connect(emp.reference, creer=False)
    try:
        communes = {
            ligne["numero"]: ligne["version"]
            for ligne in ref.execute("SELECT numero, version FROM commune").fetchall()
        }
        participants = ref.execute("SELECT numero, projet, numero_local FROM commune_projet")
        a_reprendre = set()
        for ligne in participants.fetchall():
            base = emp.projets.get(ligne["projet"])
            if base is None:
                continue
            if _version_copie(base, ligne["numero_local"]) < communes[ligne["numero"]]:
                a_reprendre.add(ligne["numero"])
    finally:
        ref.close()
    return sorted(a_reprendre)


def _version_copie(base: Path, numero_local: str) -> int:
    conn = db.connect(base, creer=False)
    try:
        ligne = conn.execute(
            "SELECT version_commune FROM commande WHERE numero = ?", (numero_local,)
        ).fetchone()
        return (ligne[0] or 0) if ligne else 0
    finally:
        conn.close()


# --- Projet qui quitte son dossier ---------------------------------------------------------------


def exiger_sans_commune(base: Path) -> None:
    """Refuse de sortir un projet d'un dossier tant qu'il a des lignes dans une commune active."""
    conn = db.connect(base, creer=False)
    try:
        ligne = conn.execute(
            "SELECT c.commune FROM commande c JOIN ligne_commande l ON l.commande_numero = c.numero"
            " WHERE c.commune IS NOT NULL AND c.archive = 0 AND l.statut_ligne <> 'Annulee'"
            " LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if ligne is not None:
        raise Conflit(
            f"Ce projet a des lignes dans la commande commune {ligne[0]} : annuler ces lignes ou"
            " archiver la commande avant de le sortir du dossier."
        )


def numeros_des_projets(bases: list[Path]) -> list[int]:
    """Numéros de communes lus dans les copies (une référence restaurée seule les a perdus)."""
    numeros = []
    for base in bases:
        conn = db.connect(base, creer=False)
        try:
            for (numero,) in conn.execute(
                "SELECT DISTINCT commune FROM commande WHERE commune IS NOT NULL"
            ).fetchall():
                correspondance = MOTIF_NUMERO.match(numero)
                if correspondance:
                    numeros.append(int(correspondance.group(1)))
        finally:
            conn.close()
    return numeros
