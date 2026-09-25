"""Comptes utilisateurs : création, rôles, blocs, permissions et invitations.

Il n'y a pas d'inscription libre : un administrateur crée chaque compte et obtient un lien
d'invitation à usage unique, qu'il transmet lui-même. En l'ouvrant, la personne choisit son
mot de passe. Un mot de passe oublié se règle par un nouveau lien, qui efface l'ancien mot
de passe et ferme les sessions ouvertes.
"""

import logging
import re
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from backend import config, db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import authentification as auth
from backend.services.droits import ADMINISTRATEUR, PERMISSIONS, ROLES, Utilisateur

journal_log = logging.getLogger(__name__)

DUREE_INVITATION = timedelta(hours=72)
MOTIF_IDENTIFIANT = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def connect(chemin: Path | None = None) -> sqlite3.Connection:
    """Connexion à la base des comptes, au schéma à jour."""
    return db.connect(chemin or config.CHEMIN_COMPTES)


def prepare_base(chemin: Path) -> int:
    """Applique les migrations de la base des comptes ; renvoie la version du schéma."""
    conn = db.connect(chemin)
    try:
        return db.apply_migrations(conn, config.DOSSIER_MIGRATIONS_COMPTES)
    finally:
        conn.close()


# --- Lecture ------------------------------------------------------------------------------------


def get_utilisateur(conn: sqlite3.Connection, utilisateur_id: int, projet: str) -> Utilisateur:
    """Utilisateur avec ses droits sur le projet (rôle None s'il n'y a pas accès)."""
    ligne = db.fetch_one(
        conn,
        "SELECT u.id, u.identifiant, u.nom, a.role FROM utilisateur u"
        " LEFT JOIN acces a ON a.utilisateur_id = u.id AND a.projet = ? WHERE u.id = ?",
        (projet, utilisateur_id),
    )
    if ligne is None:
        raise Introuvable(f"Utilisateur {utilisateur_id} introuvable.")
    blocs = conn.execute(
        "SELECT bloc_code FROM utilisateur_bloc WHERE utilisateur_id = ? AND projet = ?",
        (utilisateur_id, projet),
    ).fetchall()
    permissions = conn.execute(
        "SELECT permission FROM utilisateur_permission WHERE utilisateur_id = ? AND projet = ?",
        (utilisateur_id, projet),
    ).fetchall()
    return Utilisateur(
        id=ligne["id"],
        identifiant=ligne["identifiant"],
        nom=ligne["nom"],
        role=ligne["role"],
        blocs=frozenset(b[0] for b in blocs),
        permissions=frozenset(p[0] for p in permissions),
    )


def list_utilisateurs(conn: sqlite3.Connection, projet: str) -> list[dict]:
    """Comptes ayant un accès au projet, avec leur état d'invitation et de connexion."""
    lignes = db.fetch_all(
        conn,
        "SELECT u.id, u.identifiant, u.nom, u.actif, u.derniere_connexion, u.cree_le, a.role,"
        " EXISTS (SELECT 1 FROM identite i WHERE i.utilisateur_id = u.id) AS a_mot_de_passe,"
        " (SELECT MAX(expire_le) FROM invitation v WHERE v.utilisateur_id = u.id"
        "   AND v.utilisee_le IS NULL AND v.expire_le > ?) AS invitation_expire_le"
        " FROM utilisateur u JOIN acces a ON a.utilisateur_id = u.id AND a.projet = ?"
        " ORDER BY u.actif DESC, u.nom",
        (auth.horodatage(auth.maintenant()), projet),
    )
    for ligne in lignes:
        droits = get_utilisateur(conn, ligne["id"], projet)
        ligne["blocs"] = sorted(droits.blocs)
        ligne["permissions"] = sorted(droits.permissions)
        ligne["actif"] = bool(ligne["actif"])
        ligne["a_mot_de_passe"] = bool(ligne["a_mot_de_passe"])
    return lignes


def count_admins(conn: sqlite3.Connection, projet: str) -> int:
    ligne = conn.execute(
        "SELECT COUNT(*) FROM acces a JOIN utilisateur u ON u.id = a.utilisateur_id"
        " WHERE a.projet = ? AND a.role = ? AND u.actif = 1",
        (projet, ADMINISTRATEUR),
    ).fetchone()
    return int(ligne[0])


# --- Écriture -----------------------------------------------------------------------------------


def _check_identite(identifiant: str | None, nom: str | None) -> None:
    if identifiant is not None and not MOTIF_IDENTIFIANT.match(identifiant):
        raise ErreurMetier("L'identifiant doit être une adresse mail (elle n'est jamais écrite).")
    if nom is not None and not 1 <= len(nom) <= 60:
        raise ErreurMetier("Le nom affiché doit compter entre 1 et 60 caractères.")


def _check_droits(role: str | None, permissions: list[str] | None) -> None:
    if role is not None and role not in ROLES:
        raise ErreurMetier(f"Rôle inconnu : « {role} ».")
    inconnues = set(permissions or []) - set(PERMISSIONS)
    if inconnues:
        raise ErreurMetier(f"Permission inconnue : « {', '.join(sorted(inconnues))} ».")


def _set_droits(
    conn: sqlite3.Connection, utilisateur_id: int, projet: str, valeurs: dict[str, Any]
) -> None:
    """Remplace le rôle, les blocs et les permissions fournis ; à appeler en transaction."""
    if valeurs.get("role") is not None:
        conn.execute(
            "INSERT INTO acces (utilisateur_id, projet, role) VALUES (?, ?, ?)"
            " ON CONFLICT (utilisateur_id, projet) DO UPDATE SET role = excluded.role",
            (utilisateur_id, projet, valeurs["role"]),
        )
    for table, colonne, cle in (
        ("utilisateur_bloc", "bloc_code", "blocs"),
        ("utilisateur_permission", "permission", "permissions"),
    ):
        if valeurs.get(cle) is None:
            continue
        # Tables et colonnes codées ci-dessus, jamais issues d'une saisie.
        conn.execute(
            f"DELETE FROM {table} WHERE utilisateur_id = ? AND projet = ?",  # noqa: S608
            (utilisateur_id, projet),
        )
        conn.executemany(
            f"INSERT INTO {table} (utilisateur_id, projet, {colonne}) VALUES (?, ?, ?)",  # noqa: S608
            [(utilisateur_id, projet, v) for v in sorted(set(valeurs[cle]))],
        )


def _existants(
    conn: sqlite3.Connection, identifiant: str | None, nom: str | None, id_: int = 0
) -> None:
    if identifiant and db.fetch_one(
        conn, "SELECT 1 FROM utilisateur WHERE identifiant = ? AND id <> ?", (identifiant, id_)
    ):
        raise Conflit(f"Un compte existe déjà pour « {identifiant} ».")
    if nom and db.fetch_one(
        conn, "SELECT 1 FROM utilisateur WHERE nom = ? AND id <> ?", (nom, id_)
    ):
        raise Conflit(f"Le nom affiché « {nom} » est déjà pris : il doit rester distinctif.")


def create_utilisateur(
    conn: sqlite3.Connection, projet: str, valeurs: dict[str, Any], par: str | None
) -> dict:
    """Crée un compte avec son accès au projet ; renvoie le compte et son invitation."""
    identifiant = valeurs["identifiant"].strip().lower()
    nom = valeurs["nom"].strip()
    _check_identite(identifiant, nom)
    _check_droits(valeurs.get("role"), valeurs.get("permissions"))
    with db.transaction(conn):
        _existants(conn, identifiant, nom)
        utilisateur_id = db.insert_row(
            conn, "utilisateur", {"identifiant": identifiant, "nom": nom}
        )
        _set_droits(conn, utilisateur_id, projet, valeurs)
        invitation = _nouvelle_invitation(conn, utilisateur_id, par)
    journal_log.info("Compte %s créé par %s (rôle %s).", identifiant, par, valeurs.get("role"))
    return {
        "utilisateur": get_utilisateur(conn, utilisateur_id, projet).description(),
        **invitation,
    }


def patch_utilisateur(
    conn: sqlite3.Connection, projet: str, utilisateur_id: int, modifs: dict[str, Any]
) -> dict:
    """Modifie nom, rôle, blocs, permissions ou état actif.

    Le dernier administrateur actif du projet ne peut être ni rétrogradé ni désactivé :
    sans lui, plus personne ne pourrait gérer les comptes depuis l'interface.
    """
    nom = modifs.get("nom").strip() if modifs.get("nom") else None
    _check_identite(None, nom)
    _check_droits(modifs.get("role"), modifs.get("permissions"))
    with db.transaction(conn):
        actuel = db.fetch_one(
            conn,
            "SELECT 1 FROM acces WHERE utilisateur_id = ? AND projet = ?",
            (utilisateur_id, projet),
        )
        if actuel is None:
            raise Introuvable(f"Utilisateur {utilisateur_id} introuvable.")
        _existants(conn, None, nom, utilisateur_id)
        if nom:
            conn.execute("UPDATE utilisateur SET nom = ? WHERE id = ?", (nom, utilisateur_id))
        if modifs.get("actif") is not None:
            conn.execute(
                "UPDATE utilisateur SET actif = ? WHERE id = ?",
                (int(modifs["actif"]), utilisateur_id),
            )
            if not modifs["actif"]:
                auth.close_sessions(conn, utilisateur_id)
        _set_droits(conn, utilisateur_id, projet, modifs)
        conn.execute(
            "UPDATE utilisateur SET modifie_le = ? WHERE id = ?",
            (auth.horodatage(auth.maintenant()), utilisateur_id),
        )
        if count_admins(conn, projet) == 0:
            raise Conflit(
                "Il doit rester au moins un administrateur actif : désigner d'abord un autre"
                " administrateur."
            )
    journal_log.info("Compte %d modifié : %s.", utilisateur_id, sorted(modifs))
    return get_utilisateur(conn, utilisateur_id, projet).description()


# --- Invitations --------------------------------------------------------------------------------


def _nouvelle_invitation(conn: sqlite3.Connection, utilisateur_id: int, par: str | None) -> dict:
    """Invalide les invitations en cours et en crée une ; à appeler en transaction."""
    jeton = auth.nouveau_jeton()
    expire = auth.maintenant() + DUREE_INVITATION
    conn.execute(
        "DELETE FROM invitation WHERE utilisateur_id = ? AND utilisee_le IS NULL",
        (utilisateur_id,),
    )
    conn.execute(
        "INSERT INTO invitation (utilisateur_id, empreinte, cree_par, expire_le)"
        " VALUES (?, ?, ?, ?)",
        (utilisateur_id, auth.empreinte_jeton(jeton), par, auth.horodatage(expire)),
    )
    return {"jeton": jeton, "expire_le": auth.horodatage(expire)}


def renew_invitation(
    conn: sqlite3.Connection, projet: str, utilisateur_id: int, par: str | None
) -> dict:
    """Nouveau lien : l'ancien mot de passe est effacé et les sessions sont fermées."""
    with db.transaction(conn):
        if not db.fetch_one(
            conn,
            "SELECT 1 FROM acces WHERE utilisateur_id = ? AND projet = ?",
            (utilisateur_id, projet),
        ):
            raise Introuvable(f"Utilisateur {utilisateur_id} introuvable.")
        conn.execute("DELETE FROM identite WHERE utilisateur_id = ?", (utilisateur_id,))
        auth.close_sessions(conn, utilisateur_id)
        invitation = _nouvelle_invitation(conn, utilisateur_id, par)
    journal_log.info("Nouveau lien d'invitation pour le compte %d, par %s.", utilisateur_id, par)
    return invitation


def _invitation_valide(conn: sqlite3.Connection, jeton: str) -> dict:
    ligne = db.fetch_one(
        conn,
        "SELECT v.id, v.utilisateur_id, u.identifiant, u.nom, u.actif FROM invitation v"
        " JOIN utilisateur u ON u.id = v.utilisateur_id"
        " WHERE v.empreinte = ? AND v.utilisee_le IS NULL AND v.expire_le > ?",
        (auth.empreinte_jeton(jeton), auth.horodatage(auth.maintenant())),
    )
    if ligne is None or not ligne["actif"]:
        raise ErreurMetier(
            "Ce lien d'invitation n'est plus valable (déjà utilisé, expiré ou remplacé)."
            " Demander un nouveau lien à un administrateur.",
            410,
        )
    return ligne


def get_invitation(conn: sqlite3.Connection, jeton: str) -> dict:
    ligne = _invitation_valide(conn, jeton)
    return {"identifiant": ligne["identifiant"], "nom": ligne["nom"]}


def accept_invitation(conn: sqlite3.Connection, jeton: str, mot_de_passe: str) -> int:
    """Enregistre le mot de passe choisi et consomme l'invitation ; renvoie l'utilisateur."""
    ligne = _invitation_valide(conn, jeton)
    auth.check_mot_de_passe(mot_de_passe, ligne["identifiant"])
    with db.transaction(conn):
        # Consommée sous verrou d'écriture : deux envois simultanés du même lien ne passent pas.
        consommee = conn.execute(
            "UPDATE invitation SET utilisee_le = ? WHERE id = ? AND utilisee_le IS NULL",
            (auth.horodatage(auth.maintenant()), ligne["id"]),
        ).rowcount
        if not consommee:
            raise ErreurMetier("Ce lien d'invitation vient d'être utilisé.", 410)
        auth.set_mot_de_passe(conn, ligne["utilisateur_id"], mot_de_passe)
        auth.close_sessions(conn, ligne["utilisateur_id"])
    journal_log.info("Mot de passe choisi pour le compte %s.", ligne["identifiant"])
    return int(ligne["utilisateur_id"])


# --- Premier administrateur ---------------------------------------------------------------------


def ensure_admin(conn: sqlite3.Connection, projet: str, identifiant: str, nom: str) -> dict:
    """Crée ou rétablit un administrateur et renvoie un lien d'invitation neuf.

    Sert au premier lancement et au secours : si plus personne ne peut entrer, la ligne de
    commande rend la main à un compte, sans passer par l'interface.
    """
    identifiant = identifiant.strip().lower()
    _check_identite(identifiant, nom)
    existant = db.fetch_one(
        conn, "SELECT id FROM utilisateur WHERE identifiant = ?", (identifiant,)
    )
    if existant is None:
        return create_utilisateur(
            conn,
            projet,
            {"identifiant": identifiant, "nom": nom, "role": ADMINISTRATEUR},
            "ligne de commande",
        )
    with db.transaction(conn):
        conn.execute("UPDATE utilisateur SET actif = 1 WHERE id = ?", (existant["id"],))
        _set_droits(conn, existant["id"], projet, {"role": ADMINISTRATEUR})
    invitation = renew_invitation(conn, projet, existant["id"], "ligne de commande")
    return {
        "utilisateur": get_utilisateur(conn, existant["id"], projet).description(),
        **invitation,
    }
