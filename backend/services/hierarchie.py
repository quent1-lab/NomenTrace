"""Hiérarchie organisme › dossier › projet : structure et droits qui en descendent.

Organismes et dossiers sont des données saisies dans l'application : leur code d'adresse
(/o/<code>/, /d/<code>/) est figé à la création, leur nom reste modifiable. Qui fait quoi :
- administrateur du serveur : crée les organismes, range les projets, tout le reste ;
- administrateur d'organisme « gestion » : dossiers, projets et membres de son organisme ;
- profils « lecture » et « achats et stock » : voient l'organisme et ses dossiers ;
- responsable achats d'un dossier : voit le dossier et le résumé de ses projets.
Le compte passé à chaque fonction est celui de la requête (`comptes.get_compte`, ou le
compte implicite du mode local, administrateur du serveur).
"""

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend import db
from backend.aiguillage import code_valide
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import communes_sync, comptes, duplication, projets, propagation, reference
from backend.services.droits import (
    ADMINISTRATEUR,
    GESTION,
    PROFILS,
    RESPONSABLE_ACHATS,
    AccesRefuse,
    Utilisateur,
)
from backend.services.projets import EmplacementsProjet, Registre

journal_log = logging.getLogger(__name__)


# Le code de la référence d'un dossier, `ref-<dossier>`, doit tenir dans 40 caractères.
LONGUEUR_DOSSIER = 30
# Celui de la référence d'un organisme, `org-<organisme>`, aussi.
LONGUEUR_ORGANISME = 36


def check_code(code: str, quoi: str) -> str:
    if not code_valide(code):
        raise ErreurMetier(
            f"Code {quoi} invalide : minuscules, chiffres et tirets, 40 caractères au plus."
        )
    return code


def _nom(nom: str | None, quoi: str) -> str:
    texte = (nom or "").strip()
    if not 1 <= len(texte) <= 80:
        raise ErreurMetier(f"Le nom {quoi} doit compter entre 1 et 80 caractères.")
    return texte


# --- Lecture ------------------------------------------------------------------------------------


def get_organisme(conn: sqlite3.Connection, code: str) -> dict:
    ligne = db.fetch_one(
        conn, "SELECT code, nom FROM organisme WHERE code = ? AND archive = 0", (code,)
    )
    if ligne is None:
        raise Introuvable(f"Organisme « {code} » introuvable.")
    return ligne


def get_dossier(conn: sqlite3.Connection, code: str) -> dict:
    ligne = db.fetch_one(
        conn,
        "SELECT code, organisme, nom, nom_projet, partage_composants FROM dossier"
        " WHERE code = ? AND archive = 0",
        (code,),
    )
    if ligne is None:
        raise Introuvable(f"Dossier « {code} » introuvable.")
    return ligne


def get_projet(conn: sqlite3.Connection, code: str) -> dict:
    ligne = db.fetch_one(
        conn,
        "SELECT p.code, p.dossier, p.nom_equipe, d.organisme FROM projet p"
        " LEFT JOIN dossier d ON d.code = p.dossier WHERE p.code = ? AND p.archive = 0",
        (code,),
    )
    if ligne is None:
        raise Introuvable(f"Projet « {code} » introuvable.")
    return ligne


def get_profil(conn: sqlite3.Connection, compte: Utilisateur, organisme: str) -> str | None:
    if compte.id is None:
        return None
    ligne = db.fetch_one(
        conn,
        "SELECT profil FROM acces_organisme WHERE utilisateur_id = ? AND organisme = ?",
        (compte.id, organisme),
    )
    return ligne["profil"] if ligne else None


def est_responsable(conn: sqlite3.Connection, compte: Utilisateur, dossier: str) -> bool:
    if compte.id is None:
        return False
    return bool(
        db.fetch_one(
            conn,
            "SELECT 1 FROM acces_dossier WHERE utilisateur_id = ? AND dossier = ?",
            (compte.id, dossier),
        )
    )


# --- Droits -------------------------------------------------------------------------------------


def exiger_serveur(compte: Utilisateur) -> None:
    if not compte.admin_serveur:
        raise AccesRefuse("Action réservée à l'administrateur du serveur.")


def peut_gerer(conn: sqlite3.Connection, compte: Utilisateur, organisme: str) -> bool:
    return compte.admin_serveur or get_profil(conn, compte, organisme) == GESTION


def exiger_gestion(conn: sqlite3.Connection, compte: Utilisateur, organisme: str) -> None:
    if not peut_gerer(conn, compte, organisme):
        raise AccesRefuse("Action réservée à un administrateur de cet organisme.")


def exiger_vue_organisme(conn: sqlite3.Connection, compte: Utilisateur, organisme: str) -> None:
    if not (compte.admin_serveur or get_profil(conn, compte, organisme)):
        raise AccesRefuse("Cet organisme ne vous est pas ouvert.")


def voit_dossier(conn: sqlite3.Connection, compte: Utilisateur, dossier: dict) -> bool:
    return bool(
        compte.admin_serveur
        or get_profil(conn, compte, dossier["organisme"])
        or est_responsable(conn, compte, dossier["code"])
    )


def exiger_vue_dossier(conn: sqlite3.Connection, compte: Utilisateur, dossier: dict) -> None:
    if not voit_dossier(conn, compte, dossier):
        raise AccesRefuse("Ce dossier ne vous est pas ouvert.")


# --- Organismes et dossiers ---------------------------------------------------------------------


REQUETES_CODE: dict[str, str] = {
    "organisme": "SELECT 1 FROM organisme WHERE code = ?",
    "dossier": "SELECT 1 FROM dossier WHERE code = ?",
}


def _code_libre(conn: sqlite3.Connection, table: str, code: str) -> None:
    if db.fetch_one(conn, REQUETES_CODE[table], (code,)):
        raise Conflit(f"Le code « {code} » est déjà pris.")


def create_organisme(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    code: str,
    nom: str,
    dossiers: tuple[Path, Path],
) -> tuple[dict, EmplacementsProjet]:
    """Crée un organisme et sa référence (projet `org-<code>`, liste des fournisseurs)."""
    exiger_serveur(compte)
    check_code(code, "d'organisme")
    if len(code) > LONGUEUR_ORGANISME:
        raise ErreurMetier(f"Code d'organisme trop long : {LONGUEUR_ORGANISME} caractères au plus.")
    with db.transaction(conn):
        _code_libre(conn, "organisme", code)
        conn.execute(
            "INSERT INTO organisme (code, nom) VALUES (?, ?)", (code, _nom(nom, "d'organisme"))
        )
    try:
        emp = reference.creer_reference_organisme(conn, dossiers, code)
    except sqlite3.Error, OSError, ErreurMetier:
        with db.transaction(conn):
            conn.execute("DELETE FROM organisme WHERE code = ?", (code,))
        raise
    journal_log.info("Organisme %s créé par %s.", code, compte.nom)
    return get_organisme(conn, code), emp


def patch_organisme(conn: sqlite3.Connection, compte: Utilisateur, code: str, nom: str) -> dict:
    get_organisme(conn, code)
    exiger_gestion(conn, compte, code)
    with db.transaction(conn):
        conn.execute(
            "UPDATE organisme SET nom = ? WHERE code = ?", (_nom(nom, "d'organisme"), code)
        )
    return get_organisme(conn, code)


def create_dossier(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    organisme: str,
    valeurs: dict[str, Any],
    dossiers: tuple[Path, Path],
) -> tuple[dict, EmplacementsProjet]:
    """Crée un dossier et sa référence (projet `ref-<code>`, réglages communs)."""
    get_organisme(conn, organisme)
    exiger_gestion(conn, compte, organisme)
    code = check_code(valeurs["code"], "de dossier")
    if len(code) > LONGUEUR_DOSSIER:
        raise ErreurMetier(f"Code de dossier trop long : {LONGUEUR_DOSSIER} caractères au plus.")
    nom_projet = (valeurs.get("nom_projet") or "").strip() or None
    with db.transaction(conn):
        _code_libre(conn, "dossier", code)
        conn.execute(
            "INSERT INTO dossier (code, organisme, nom, nom_projet) VALUES (?, ?, ?, ?)",
            (code, organisme, _nom(valeurs.get("nom"), "du dossier"), nom_projet),
        )
    try:
        emp = reference.creer_reference(conn, dossiers, code)
    except sqlite3.Error, OSError, ErreurMetier:
        with db.transaction(conn):
            conn.execute("DELETE FROM dossier WHERE code = ?", (code,))
        raise
    journal_log.info("Dossier %s créé dans %s par %s.", code, organisme, compte.nom)
    return get_dossier(conn, code), emp


def patch_dossier(
    conn: sqlite3.Connection, compte: Utilisateur, code: str, modifs: dict[str, Any]
) -> dict:
    dossier = get_dossier(conn, code)
    exiger_gestion(conn, compte, dossier["organisme"])
    with db.transaction(conn):
        if "nom" in modifs:
            conn.execute(
                "UPDATE dossier SET nom = ? WHERE code = ?",
                (_nom(modifs["nom"], "du dossier"), code),
            )
        if "nom_projet" in modifs:
            nom_projet = (modifs["nom_projet"] or "").strip() or None
            conn.execute("UPDATE dossier SET nom_projet = ? WHERE code = ?", (nom_projet, code))
        if modifs.get("partage_composants") is not None:
            conn.execute(
                "UPDATE dossier SET partage_composants = ? WHERE code = ?",
                (int(bool(modifs["partage_composants"])), code),
            )
            journal_log.info(
                "Mise en commun des composants du dossier %s %s par %s.",
                code,
                "activée" if modifs["partage_composants"] else "désactivée",
                compte.nom,
            )
    return get_dossier(conn, code)


def _admin_projet(conn: sqlite3.Connection, compte: Utilisateur, code: str) -> bool:
    return compte.id is not None and comptes.get_utilisateur(conn, compte.id, code).admin


def _exiger_patch_projet(
    conn: sqlite3.Connection, compte: Utilisateur, projet: dict, modifs: dict[str, Any]
) -> None:
    """Tous les droits sont vérifiés avant la première écriture."""
    if reference.est_reference(conn, projet["code"]):
        raise AccesRefuse("La référence d'un dossier ne se range ni ne se renomme.")
    gere = bool(projet["organisme"]) and peut_gerer(conn, compte, projet["organisme"])
    if "dossier" in modifs and modifs["dossier"] != projet["dossier"]:
        exiger_serveur(compte)
        if modifs["dossier"] is not None:
            get_dossier(conn, modifs["dossier"])
    if "budget_ht" in modifs and not gere:
        raise AccesRefuse("Le budget d'un projet se fixe par l'administrateur de l'organisme.")
    if "nom_equipe" in modifs and not (
        compte.admin_serveur or gere or _admin_projet(conn, compte, projet["code"])
    ):
        raise AccesRefuse("Le nom d'équipe se règle par un administrateur du projet.")


def patch_projet(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    code: str,
    modifs: dict[str, Any],
    registre: Registre,
) -> dict:
    """Range un projet dans un dossier (serveur), change son nom d'équipe ou son budget.

    Ranger : le projet donne la référence du dossier si elle est neuve, la reçoit sinon ;
    sortir d'un dossier lève le verrou des réglages imposés, valeurs gardées. Le budget est
    fixé par l'administrateur de l'organisme, depuis la page du dossier.
    """
    projet = get_projet(conn, code)
    _exiger_patch_projet(conn, compte, projet, modifs)
    rapport = None
    if "dossier" in modifs and modifs["dossier"] != projet["dossier"]:
        if projet["dossier"] is not None and code in registre.projets:
            communes_sync.exiger_sans_commune(registre.projets[code].base)
        if modifs["dossier"] is None:
            reference.sortir(registre, code)
        else:
            rapport = reference.ranger(
                conn, registre, code, modifs["dossier"], ancien_dossier=projet["dossier"]
            )
    if "budget_ht" in modifs:
        emp = registre.projets.get(code)
        if emp is None:
            raise ErreurMetier(f"Le projet « {code} » est hors ligne.", 503)
        propagation.ecrire_budget(emp.base, modifs["budget_ht"], compte.nom)
    with db.transaction(conn):
        if "dossier" in modifs:
            conn.execute("UPDATE projet SET dossier = ? WHERE code = ?", (modifs["dossier"], code))
        if "nom_equipe" in modifs:
            nom = (modifs["nom_equipe"] or "").strip() or None
            if nom is not None:
                nom = _nom(nom, "d'équipe")
            conn.execute("UPDATE projet SET nom_equipe = ? WHERE code = ?", (nom, code))
    journal_log.info("Projet %s modifié par %s : %s.", code, compte.nom, sorted(modifs))
    return {**get_projet(conn, code), "propagation": rapport}


# --- Membres d'un organisme, responsables d'un dossier ------------------------------------------


def _check_profil(profil: str) -> None:
    if profil not in PROFILS:
        raise ErreurMetier(f"Profil inconnu : « {profil} ».")


def invite_membre(
    conn: sqlite3.Connection, compte: Utilisateur, organisme: str, valeurs: dict[str, Any]
) -> dict:
    """Donne un profil d'organisme à un compte, créé au besoin avec son lien d'invitation."""
    get_organisme(conn, organisme)
    exiger_gestion(conn, compte, organisme)
    _check_profil(valeurs["profil"])
    cree = comptes.create_compte(conn, valeurs["identifiant"], valeurs["nom"], compte.nom)
    with db.transaction(conn):
        if db.fetch_one(
            conn,
            "SELECT 1 FROM acces_organisme WHERE utilisateur_id = ? AND organisme = ?",
            (cree["id"], organisme),
        ):
            raise Conflit("Ce compte a déjà un profil dans cet organisme.")
        conn.execute(
            "INSERT INTO acces_organisme (utilisateur_id, organisme, profil) VALUES (?, ?, ?)",
            (cree["id"], organisme, valeurs["profil"]),
        )
    journal_log.info(
        "Profil %s dans %s pour le compte %d.", valeurs["profil"], organisme, cree["id"]
    )
    return cree


def set_profil(
    conn: sqlite3.Connection, compte: Utilisateur, organisme: str, utilisateur_id: int, profil: str
) -> None:
    exiger_gestion(conn, compte, organisme)
    _check_profil(profil)
    with db.transaction(conn):
        modifie = conn.execute(
            "UPDATE acces_organisme SET profil = ? WHERE utilisateur_id = ? AND organisme = ?",
            (profil, utilisateur_id, organisme),
        ).rowcount
    if not modifie:
        raise Introuvable(f"Membre {utilisateur_id} introuvable dans cet organisme.")


def retirer_membre(
    conn: sqlite3.Connection, compte: Utilisateur, organisme: str, utilisateur_id: int
) -> None:
    exiger_gestion(conn, compte, organisme)
    with db.transaction(conn):
        retire = conn.execute(
            "DELETE FROM acces_organisme WHERE utilisateur_id = ? AND organisme = ?",
            (utilisateur_id, organisme),
        ).rowcount
    if not retire:
        raise Introuvable(f"Membre {utilisateur_id} introuvable dans cet organisme.")


def list_candidats(conn: sqlite3.Connection, dossier: str) -> list[dict]:
    """Responsables achats possibles : les membres des projets du dossier."""
    return db.fetch_all(
        conn,
        "SELECT DISTINCT u.id, u.nom FROM utilisateur u"
        " JOIN acces a ON a.utilisateur_id = u.id"
        " JOIN projet p ON p.code = a.projet AND p.archive = 0 AND p.reference = 0"
        " WHERE p.dossier = ? AND u.actif = 1 ORDER BY u.nom",
        (dossier,),
    )


def add_responsable(
    conn: sqlite3.Connection, compte: Utilisateur, code: str, utilisateur_id: int
) -> None:
    dossier = get_dossier(conn, code)
    exiger_gestion(conn, compte, dossier["organisme"])
    if utilisateur_id not in {c["id"] for c in list_candidats(conn, code)}:
        raise ErreurMetier(
            "Le responsable achats se choisit parmi les membres des projets du dossier."
        )
    with db.transaction(conn):
        conn.execute(
            "INSERT OR IGNORE INTO acces_dossier (utilisateur_id, dossier, role) VALUES (?, ?, ?)",
            (utilisateur_id, code, RESPONSABLE_ACHATS),
        )


def retirer_responsable(
    conn: sqlite3.Connection, compte: Utilisateur, code: str, utilisateur_id: int
) -> None:
    dossier = get_dossier(conn, code)
    exiger_gestion(conn, compte, dossier["organisme"])
    with db.transaction(conn):
        retire = conn.execute(
            "DELETE FROM acces_dossier WHERE utilisateur_id = ? AND dossier = ?",
            (utilisateur_id, code),
        ).rowcount
    if not retire:
        raise Introuvable(f"Responsable {utilisateur_id} introuvable dans ce dossier.")


# --- Projets ------------------------------------------------------------------------------------


def _reprise(
    modele: str | None, dossiers: tuple[Path, Path], auteur: str
) -> Callable[[Path], object] | None:
    """Préparation d'une base neuve reprise d'un projet modèle (réglages propres)."""
    if modele is None:
        return None
    source = projets.emplacements(dossiers[0], dossiers[1], modele).base
    return lambda base: duplication.copier_reglages_propres(source, base, auteur)


def create_projet(
    conn: sqlite3.Connection,
    compte: Utilisateur,
    code_dossier: str,
    valeurs: dict[str, Any],
    dossiers: tuple[Path, Path],
) -> tuple[EmplacementsProjet, dict | None]:
    """Crée un projet dans un dossier ; invite au besoin son administrateur.

    `dossiers` : dossier des données et dossier d'échange de l'instance. Le nom du projet
    vient du dossier, le préfixe de la saisie ; tous deux sont figés ici pour le projet.
    """
    dossier = get_dossier(conn, code_dossier)
    exiger_gestion(conn, compte, dossier["organisme"])
    code = check_code(valeurs["code"], "de projet")
    if code.startswith(reference.PREFIXES_RESERVES):
        raise ErreurMetier("Les codes « ref-… » et « org-… » sont réservés aux références.")
    modele = valeurs.get("modele")
    if modele is not None and get_projet(conn, modele)["dossier"] != code_dossier:
        raise ErreurMetier("Le projet modèle doit appartenir au même dossier.")
    reglages = {"prefixe_id": valeurs["prefixe_id"]}
    if dossier["nom_projet"]:
        reglages["nom_projet"] = dossier["nom_projet"]
    emp = projets.creer_projet(
        conn,
        *dossiers,
        {
            "code": code,
            "dossier": code_dossier,
            "nom_equipe": _nom(valeurs["nom_equipe"], "d'équipe"),
        },
        reglages,
        _reprise(modele, dossiers, compte.nom),
    )
    invitation = None
    if valeurs.get("admin_identifiant"):
        invitation = comptes.create_utilisateur(
            conn,
            code,
            {
                "identifiant": valeurs["admin_identifiant"],
                "nom": valeurs.get("admin_nom") or valeurs["admin_identifiant"].split("@")[0],
                "role": ADMINISTRATEUR,
            },
            compte.nom,
        )
    return emp, invitation
