"""Réglages imposés par un dossier : empreinte, synchronisation et initialisation.

La référence d'un dossier est la base de son projet de référence (`ref-<dossier>`). Ses
tables imposées (TABLES) sont recopiées dans chaque projet du dossier par une
synchronisation complète, dans une seule transaction, la référence attachée à la base du
projet. Un projet est à jour quand l'empreinte qu'il garde (`reglages_imposes.empreinte`,
écrite dans la même transaction) égale celle de la référence : une synchronisation
interrompue, une restauration du projet ou de la référence se rattrapent d'elles-mêmes.

Rien n'est jamais perdu dans un projet : une ligne absente de la référence est supprimée
seulement si rien ne l'utilise ; sinon un bloc reste (avec ses composants actifs), une
valeur de liste ou d'attribut est désactivée, un attribut aussi. Chaque changement laisse
une ligne de journal.
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import journal, sauvegardes

journal_log = logging.getLogger(__name__)

LISTES_IMPOSEES: tuple[str, ...] = ("mode_appro", "criticite", "type_mouvement", "type_frais")
# Paramètres recopiés de la référence ; le nom du projet vient du dossier.
CLES_IMPOSEES: tuple[str, ...] = (
    "taux_tva_defaut",
    "champs_obligatoires",
    "champs_obligatoires_portee",
    "etablissement_nom",
    "adresse_livraison",
    "adresse_facturation",
    "contact_achats_nom",
    "contact_achats_mail",
    "contact_achats_tel",
)


@dataclass(frozen=True)
class Table:
    """Table imposée : clé, colonnes recopiées et lignes concernées (filtre SQL écrit ici)."""

    nom: str
    cle: tuple[str, ...]
    colonnes: tuple[str, ...]
    filtre: str = "1"


TABLES: tuple[Table, ...] = (
    Table("bloc", ("code",), ("nom", "ordre", "description", "archive")),
    Table(
        "valeur_liste",
        ("liste", "code"),
        ("libelle", "ordre", "actif", "systeme", "sens"),
        "liste IN ('mode_appro', 'criticite', 'type_mouvement', 'type_frais')",
    ),
    Table("attribut", ("code",), ("libelle", "type", "unite", "ordre", "actif", "obligatoire")),
    Table("attribut_valeur", ("attribut_code", "code"), ("libelle", "ordre", "actif")),
    Table(
        "parametre",
        ("cle",),
        ("valeur",),
        "cle IN ('taux_tva_defaut', 'champs_obligatoires', 'champs_obligatoires_portee',"
        " 'etablissement_nom', 'adresse_livraison', 'adresse_facturation',"
        " 'contact_achats_nom', 'contact_achats_mail', 'contact_achats_tel')",
    ),
    Table("logo", ("id",), ("type_mime", "contenu", "largeur", "hauteur", "modifie_le")),
)

# Où une valeur de liste imposée est utilisée (une valeur utilisée n'est jamais supprimée).
USAGES_LISTE: dict[str, str] = {
    "mode_appro": "SELECT 1 FROM composant WHERE mode_appro = ? LIMIT 1",
    "criticite": "SELECT 1 FROM composant WHERE criticite = ? LIMIT 1",
    "type_mouvement": "SELECT 1 FROM mouvement_stock WHERE type_mouvement = ? LIMIT 1",
    "type_frais": "SELECT 1 FROM frais_commande WHERE type_frais = ? LIMIT 1",
}


@dataclass
class Rapport:
    """Ce qu'une synchronisation a fait, et ce qu'elle n'a pas pu faire."""

    modifiees: int = 0
    supprimees: int = 0
    desactivees: int = 0
    signalements: list[str] = field(default_factory=list)

    def resume(self) -> dict:
        return {
            "modifiees": self.modifiees,
            "supprimees": self.supprimees,
            "desactivees": self.desactivees,
            "signalements": self.signalements,
        }


# --- Lecture ------------------------------------------------------------------------------------


def _lignes(conn: sqlite3.Connection, schema: str, table: Table) -> dict[tuple, dict]:
    """Lignes imposées d'une table, par clé. Noms de schéma et de table écrits dans ce module."""
    colonnes = ", ".join((*table.cle, *table.colonnes))
    requete = f"SELECT {colonnes} FROM {schema}.{table.nom} WHERE {table.filtre}"  # noqa: S608
    return {tuple(r[c] for c in table.cle): dict(r) for r in conn.execute(requete).fetchall()}


def _canonique(valeur: Any) -> Any:
    return valeur.hex() if isinstance(valeur, bytes) else valeur


def empreinte(
    conn: sqlite3.Connection, schema: str, nom_projet: str | None, schema_org: str | None = None
) -> str:
    """Empreinte du contenu imposé : référence du dossier (attachée sous `schema`), nom du
    projet et, s'il y en a une, liste des fournisseurs de l'organisme (sous `schema_org`)."""
    from backend.services import fournisseurs_communs

    contenu: dict[str, Any] = {"nom_projet": nom_projet}
    if schema_org is not None:
        contenu["fournisseur"] = fournisseurs_communs.contenu(conn, schema_org)
    for table in TABLES:
        lignes = _lignes(conn, schema, table)
        contenu[table.nom] = [
            [_canonique(ligne[c]) for c in (*table.cle, *table.colonnes)]
            for _, ligne in sorted(lignes.items(), key=lambda paire: json.dumps(paire[0]))
        ]
    texte = json.dumps(contenu, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texte.encode()).hexdigest()


def empreinte_base(chemin: Path, nom_projet: str | None, organisme: Path | None = None) -> str:
    conn = db.connect(chemin, creer=False)
    try:
        if organisme is None:
            return empreinte(conn, "main", nom_projet)
        conn.execute("ATTACH DATABASE ? AS org", (f"{organisme.resolve().as_uri()}?mode=ro",))
        try:
            return empreinte(conn, "main", nom_projet, "org")
        finally:
            conn.execute("DETACH DATABASE org")
    finally:
        conn.close()


def etat(conn: sqlite3.Connection) -> dict:
    return db.fetch_one(conn, "SELECT * FROM reglages_imposes WHERE id = 1") or {}


# --- Écriture -----------------------------------------------------------------------------------


def _inserer(conn: sqlite3.Connection, table: Table, ligne: dict) -> None:
    colonnes = (*table.cle, *table.colonnes)
    marques = ", ".join("?" for _ in colonnes)
    conn.execute(
        f"INSERT INTO main.{table.nom} ({', '.join(colonnes)}) VALUES ({marques})",  # noqa: S608
        [ligne[c] for c in colonnes],
    )


def _ou(table: Table) -> str:
    return " AND ".join(f"{c} = ?" for c in table.cle)


def _mettre_a_jour(conn: sqlite3.Connection, table: Table, cle: tuple, valeurs: dict) -> None:
    affectations = ", ".join(f"{c} = ?" for c in valeurs)
    conn.execute(
        f"UPDATE main.{table.nom} SET {affectations} WHERE {_ou(table)}",  # noqa: S608
        [*valeurs.values(), *cle],
    )


def _supprimer(conn: sqlite3.Connection, table: Table, cle: tuple, ligne: dict) -> None:
    conn.execute(f"DELETE FROM main.{table.nom} WHERE {_ou(table)}", cle)  # noqa: S608
    resume = json.dumps({k: _canonique(v) for k, v in ligne.items() if k != "contenu"})
    journal.write_journal(conn, table.nom, ":".join(map(str, cle)), "suppression", resume, None)


def _utilisee(conn: sqlite3.Connection, table: Table, cle: tuple) -> bool:
    """Une ligne absente de la référence sert-elle encore dans ce projet ?"""
    if table.nom == "valeur_liste":
        liste, code = cle
        return bool(conn.execute(USAGES_LISTE[liste], (code,)).fetchone())
    if table.nom == "attribut_valeur":
        return bool(
            conn.execute(
                "SELECT 1 FROM composant_attribut WHERE attribut_code = ? AND valeur_texte = ?"
                " LIMIT 1",
                cle,
            ).fetchone()
        )
    return False


def _composants_actifs(conn: sqlite3.Connection, bloc: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM composant WHERE bloc_code = ? AND archive = 0", (bloc,)
    ).fetchone()[0]


def _retirer(
    conn: sqlite3.Connection, table: Table, cle: tuple, ligne: dict, rapport: Rapport
) -> None:
    """Ligne du projet absente de la référence : supprimée, archivée ou désactivée."""
    etiquette = ":".join(map(str, cle))
    if table.nom == "bloc":
        if ligne["archive"]:
            return
        if _composants_actifs(conn, cle[0]):
            rapport.signalements.append(
                f"Bloc « {cle[0]} » absent des paramètres communs : gardé, il porte des composants."
            )
            return
        _mettre_a_jour(conn, table, cle, {"archive": 1})
        journal.write_journal(conn, "bloc", cle[0], "archive", 0, 1)
        rapport.desactivees += 1
    elif table.nom == "attribut" or (
        table.nom in ("valeur_liste", "attribut_valeur") and _utilisee(conn, table, cle)
    ):
        if ligne.get("systeme") or not ligne["actif"]:
            return
        _mettre_a_jour(conn, table, cle, {"actif": 0})
        journal.write_journal(conn, table.nom, etiquette, "actif", 1, 0)
        rapport.desactivees += 1
        if table.nom != "attribut":
            rapport.signalements.append(f"Valeur « {etiquette} » désactivée : elle est utilisée.")
    elif not ligne.get("systeme"):
        _supprimer(conn, table, cle, ligne)
        rapport.supprimees += 1


def _accorder(
    conn: sqlite3.Connection, table: Table, cle: tuple, voulu: dict, actuel: dict, rapport: Rapport
) -> None:
    """Ligne présente des deux côtés : seules les colonnes qui diffèrent sont réécrites."""
    changes = {c: voulu[c] for c in table.colonnes if voulu[c] != actuel[c]}
    if table.nom == "bloc" and changes.get("archive") == 1 and _composants_actifs(conn, cle[0]):
        del changes["archive"]
        rapport.signalements.append(
            f"Bloc « {cle[0]} » archivé dans les paramètres communs : gardé, il porte des"
            " composants actifs."
        )
    if table.nom == "attribut" and "type" in changes:
        raise ErreurMetier(f"Attribut « {cle[0]} » d'un autre type que dans la référence.")
    if not changes:
        return
    _mettre_a_jour(conn, table, cle, changes)
    for colonne, valeur in changes.items():
        if colonne != "contenu":
            journal.write_journal(
                conn, table.nom, ":".join(map(str, cle)), colonne, actuel[colonne], valeur
            )
    rapport.modifiees += 1


def _synchroniser_table(conn: sqlite3.Connection, table: Table, rapport: Rapport) -> None:
    voulues = _lignes(conn, "ref", table)
    actuelles = _lignes(conn, "main", table)
    for cle, ligne in voulues.items():
        if cle not in actuelles:
            _inserer(conn, table, ligne)
            journal.write_journal(
                conn, table.nom, ":".join(map(str, cle)), "creation", None, "copiée du dossier"
            )
            rapport.modifiees += 1
        else:
            _accorder(conn, table, cle, ligne, actuelles[cle], rapport)
    # Valeurs d'attribut avant leurs attributs : un attribut n'est jamais supprimé.
    for cle, ligne in actuelles.items():
        if cle not in voulues:
            _retirer(conn, table, cle, ligne, rapport)


def _nom_projet(conn: sqlite3.Connection, nom_projet: str | None, rapport: Rapport) -> None:
    if nom_projet is None:
        return
    actuel = conn.execute("SELECT valeur FROM main.parametre WHERE cle = 'nom_projet'").fetchone()
    if actuel is not None and actuel[0] == nom_projet:
        return
    conn.execute(
        "INSERT INTO main.parametre (cle, valeur) VALUES ('nom_projet', ?)"
        " ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur",
        (nom_projet,),
    )
    journal.write_journal(
        conn, "parametre", "nom_projet", "valeur", actuel[0] if actuel else None, nom_projet
    )
    rapport.modifiees += 1


def _sous_verrou_leve(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE main.reglages_imposes SET propagation = 1 WHERE id = 1")


def synchroniser(
    projet: Path,
    reference: Path,
    dossier: str,
    nom_projet: str | None,
    sauvegardes_projet: Path | None = None,
    organisme: Path | None = None,
) -> Rapport:
    """Accorde les tables imposées d'un projet à la référence de son dossier, et sa liste de
    fournisseurs à celle de son organisme s'il y en a une, puis pose le verrou.

    Sans effet si le projet est déjà à jour (même empreinte). Une sauvegarde du projet est
    prise avant tout changement.
    """
    from backend.services import fournisseurs_communs

    voulue = empreinte_base(reference, nom_projet, organisme)
    conn = db.connect(projet, f"paramètres communs · {dossier}", creer=False)
    try:
        courant = etat(conn)
        if (
            courant.get("empreinte") == voulue
            and courant.get("actif")
            and courant.get("dossier") == dossier
        ):
            return Rapport()
        if sauvegardes_projet is not None:
            sauvegardes.create_sauvegarde(projet, sauvegardes_projet)
        conn.execute("ATTACH DATABASE ? AS ref", (f"{reference.resolve().as_uri()}?mode=ro",))
        if organisme is not None:
            conn.execute("ATTACH DATABASE ? AS org", (f"{organisme.resolve().as_uri()}?mode=ro",))
        rapport = Rapport()
        with db.transaction(conn):
            _sous_verrou_leve(conn)
            for table in TABLES:
                _synchroniser_table(conn, table, rapport)
            _nom_projet(conn, nom_projet, rapport)
            if organisme is not None:
                fournisseurs_communs.synchroniser(conn, rapport)
            conn.execute(
                "UPDATE main.reglages_imposes SET actif = 1, propagation = 0, dossier = ?,"
                " empreinte = ? WHERE id = 1",
                (dossier, voulue),
            )
        conn.execute("DETACH DATABASE ref")
        if organisme is not None:
            conn.execute("DETACH DATABASE org")
    finally:
        conn.close()
    journal_log.info(
        "Projet %s accordé au dossier %s : %s", projet.parent.name, dossier, rapport.resume()
    )
    return rapport


def lever_verrou(projet: Path) -> None:
    """Projet sorti de son dossier : ses réglages deviennent les siens, valeurs gardées."""
    conn = db.connect(projet, creer=False)
    try:
        with db.transaction(conn):
            conn.execute(
                "UPDATE reglages_imposes SET actif = 0, dossier = NULL, empreinte = NULL"
                " WHERE id = 1"
            )
    finally:
        conn.close()


def conflits(projet: Path, reference: Path) -> list[str]:
    """Différences qui empêchent d'accorder un projet à la référence : type d'attribut."""
    conn = db.connect(projet, creer=False)
    try:
        conn.execute("ATTACH DATABASE ? AS ref", (f"{reference.resolve().as_uri()}?mode=ro",))
        lignes = conn.execute(
            "SELECT a.code, a.type, r.type AS type_ref FROM main.attribut a"
            " JOIN ref.attribut r ON r.code = a.code WHERE a.type <> r.type"
        ).fetchall()
        conn.execute("DETACH DATABASE ref")
    finally:
        conn.close()
    return [
        f"Attribut « {ligne['code']} » : {ligne['type']} dans le projet, {ligne['type_ref']}"
        " dans le dossier."
        for ligne in lignes
    ]


def initialiser_reference(reference: Path, projet: Path, dossier: str) -> str | None:
    """Copie inverse : la référence prend les réglages imposés du projet, qui ne change pas.

    Renvoie le nom du projet, que le dossier reprend.
    """
    conn = db.connect(reference, f"paramètres communs · {dossier}", creer=False)
    try:
        conn.execute("ATTACH DATABASE ? AS ref", (f"{projet.resolve().as_uri()}?mode=ro",))
        rapport = Rapport()
        with db.transaction(conn):
            for table in TABLES:
                _synchroniser_table(conn, table, rapport)
            nom = conn.execute(
                "SELECT valeur FROM ref.parametre WHERE cle = 'nom_projet'"
            ).fetchone()
            conn.execute(
                "UPDATE main.reglages_imposes SET initialisee = 1, dossier = ? WHERE id = 1",
                (dossier,),
            )
        conn.execute("DETACH DATABASE ref")
    finally:
        conn.close()
    return nom[0] if nom else None


def marquer_initialisee(reference: Path, dossier: str | None) -> None:
    conn = db.connect(reference, creer=False)
    try:
        with db.transaction(conn):
            conn.execute(
                "UPDATE reglages_imposes SET initialisee = 1, dossier = ? WHERE id = 1", (dossier,)
            )
    finally:
        conn.close()


def est_initialisee(reference: Path) -> bool:
    conn = db.connect(reference, creer=False)
    try:
        return bool(etat(conn).get("initialisee"))
    finally:
        conn.close()


def ecrire_budget(projet: Path, budget: float | None, auteur: str) -> None:
    """Budget global d'un projet rangé, fixé depuis la page du dossier (verrou levé un instant)."""
    conn = db.connect(projet, auteur, creer=False)
    try:
        with db.transaction(conn):
            _sous_verrou_leve(conn)
            ancien = conn.execute("SELECT valeur FROM parametre WHERE cle = 'budget_ht'").fetchone()
            texte = None if budget is None else str(budget)
            conn.execute(
                "INSERT INTO parametre (cle, valeur) VALUES ('budget_ht', ?)"
                " ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur",
                (texte,),
            )
            journal.write_journal(
                conn, "parametre", "budget_ht", "valeur", ancien[0] if ancien else None, texte
            )
            conn.execute("UPDATE reglages_imposes SET propagation = 0 WHERE id = 1")
    finally:
        conn.close()
