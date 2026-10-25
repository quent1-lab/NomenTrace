"""Catalogue du dossier (phase 17) : proposer une référence déjà saisie par un autre projet.

Quand le dossier met ses composants en commun (`dossier.partage_composants`), la création
d'un composant cherche, dans les bases des autres projets du dossier, les références qui
ressemblent à ce qui est tapé (moteur des doublons de l'import). Rien n'est copié à
l'avance ni indexé : chaque recherche lit les bases, composants non archivés, projets hors
ligne sautés. La liste d'un autre projet n'est jamais renvoyée en entier : seulement les
meilleures propositions, réduites à la référence (ni quantités, ni statuts, ni commandes).

Reprendre une proposition préremplit la création ; le composant reçoit son identifiant et
son prix dans le projet, sans lien en base avec l'original (une ligne de journal le dit).
Ses fiches techniques sont recopiées dans la même transaction que la création.
"""

import logging
import sqlite3
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import attributs, composants, documents, hierarchie, journal, reference
from backend.services import import_doublons as doublons
from backend.services.projets import EmplacementsProjet, Registre

journal_log = logging.getLogger(__name__)

LONGUEUR_MINIMALE = 3
FICHE_TECHNIQUE = "Fiche technique"
# Champs recopiés par une reprise ; quantités, statuts, criticité et notes restent à saisir.
CHAMPS_REPRIS: tuple[str, ...] = (
    "bloc_code",
    "fonction",
    "designation",
    "ref_fabricant",
    "fabricant",
    "fournisseur_nom",
    "lien_produit",
    "pu_releve",
    "base_prix_releve",
    "taux_tva",
)
SQL_COMPOSANTS = (
    "SELECT c.id, c.fonction, c.designation, c.ref_fabricant, c.fabricant, c.fournisseur_nom,"
    " v.qte_recue,"
    " (SELECT COUNT(*) FROM document d WHERE d.composant_id = c.id AND d.archive = 0"
    "  AND d.type_document = 'Fiche technique') AS nb_fiches"
    " FROM composant c JOIN v_composant v ON v.id = c.id WHERE c.archive = 0"
)


def _sources(
    conn_comptes: sqlite3.Connection, registre: Registre, projet: str
) -> dict[str, EmplacementsProjet] | None:
    """Autres projets en ligne du dossier ; None si le dossier ne partage pas ses composants."""
    ligne = hierarchie.get_projet(conn_comptes, projet)
    if ligne["dossier"] is None:
        return None
    dossier = hierarchie.get_dossier(conn_comptes, ligne["dossier"])
    if not dossier["partage_composants"]:
        return None
    codes = reference.projets_du_dossier(conn_comptes, dossier["code"])
    return {c: registre.projets[c] for c in codes if c != projet and c in registre.projets}


def _equipe(conn_comptes: sqlite3.Connection, code: str) -> str:
    ligne = conn_comptes.execute("SELECT nom_equipe FROM projet WHERE code = ?", (code,)).fetchone()
    return (ligne[0] if ligne else None) or code


def _lire(base: Path, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    lecture = db.connect(base, creer=False)
    try:
        return db.fetch_all(lecture, sql, params)
    finally:
        lecture.close()


# Composants et empreintes de chaque base lue, gardés tant que ses fichiers (base et
# journal WAL) n'ont pas changé : la lecture et les empreintes coûtent plus que la
# comparaison. Mémoire du processus seulement, rien n'est écrit.
_lus: dict[Path, tuple[tuple, list[tuple[dict, doublons.Empreinte]]]] = {}


def _signature(base: Path) -> tuple:
    signature = []
    for fichier in (base, base.with_name(base.name + "-wal")):
        try:
            etat = fichier.stat()
        except FileNotFoundError:
            signature.append(None)
            continue
        signature.append((etat.st_mtime_ns, etat.st_size))
    return tuple(signature)


def _composants(base: Path) -> list[tuple[dict, doublons.Empreinte]]:
    signature = _signature(base)
    garde = _lus.get(base)
    if garde is not None and garde[0] == signature:
        return garde[1]
    lignes = _lire(base, SQL_COMPOSANTS)
    resultat = [(ligne, doublons.empreinte(ligne["id"], ligne)) for ligne in lignes]
    _lus[base] = (signature, resultat)
    return resultat


def search_catalogue(
    conn: sqlite3.Connection,
    conn_comptes: sqlite3.Connection,
    registre: Registre,
    projet: str,
    saisie: dict[str, str | None],
) -> dict:
    """Propositions du dossier et doublons du projet pour ce qui est en cours de saisie.

    `saisie` porte `designation`, `ref_fabricant` et `fonction`. Un doublon du projet n'est
    signalé que s'il est sûr (référence identique, citée, ou libellés très proches).
    """
    sources = _sources(conn_comptes, registre, projet)
    vide = {"actif": sources is not None, "propositions": [], "dans_le_projet": []}
    if max(len((saisie.get(c) or "").strip()) for c in ("designation", "ref_fabricant")) < (
        LONGUEUR_MINIMALE
    ):
        return vide
    cherche = doublons.empreinte(None, saisie)
    locaux = _composants(registre.projets[projet].base)
    sur_place = doublons.search(cherche, [e for _, e in locaux])
    par_id = {c["id"]: c for c, _ in locaux}
    vide["dans_le_projet"] = [
        {"id": t["cle"], "designation": par_id[t["cle"]]["designation"]}
        for t in sur_place
        if t["fusion"]
    ]
    if not sources:
        return vide
    lus: dict[tuple[str, str], dict] = {}
    empreintes: list[doublons.Empreinte] = []
    for code, emp in sources.items():
        for ligne, empreinte in _composants(emp.base):
            lus[(code, ligne["id"])] = ligne
            empreintes.append(replace(empreinte, cle=(code, ligne["id"])))
    trouves = doublons.search(cherche, empreintes)
    vide["propositions"] = [_proposition(conn_comptes, t, lus[t["cle"]]) for t in trouves]
    return vide


def _proposition(conn_comptes: sqlite3.Connection, trouve: dict, ligne: dict) -> dict:
    code, identifiant = trouve["cle"]
    return {
        "projet": code,
        "id": identifiant,
        "equipe": _equipe(conn_comptes, code),
        "designation": ligne["designation"],
        "ref_fabricant": ligne["ref_fabricant"],
        "fabricant": ligne["fabricant"],
        "fournisseur_nom": ligne["fournisseur_nom"],
        "recu": (ligne["qte_recue"] or 0) > 0,
        "nb_fiches": ligne["nb_fiches"],
        "motif": trouve["motif"],
    }


def _source(
    conn_comptes: sqlite3.Connection, registre: Registre, projet: str, source: str
) -> EmplacementsProjet:
    sources = _sources(conn_comptes, registre, projet)
    if sources is None:
        raise ErreurMetier("Ce dossier ne met pas ses composants en commun.", 403)
    if source not in sources:
        raise Introuvable(f"Projet « {source} » introuvable dans le dossier ou hors ligne.")
    return sources[source]


def _date_prix(base: Path, identifiant: str, cree_le: str) -> str:
    """Date du dernier relevé du prix : sa dernière écriture au journal, sinon la création."""
    lignes = _lire(
        base,
        "SELECT MAX(horodatage) AS quand FROM journal"
        " WHERE table_cible = 'composant' AND cle_cible = ? AND champ = 'pu_releve'",
        (identifiant,),
    )
    return (lignes[0]["quand"] if lignes and lignes[0]["quand"] else cree_le)[:10]


def get_reprise(
    conn: sqlite3.Connection,
    conn_comptes: sqlite3.Connection,
    registre: Registre,
    projet: str,
    source: str,
    identifiant: str,
) -> dict:
    """Ce qu'une reprise recopie d'un composant d'un autre projet du dossier.

    Fournisseur et caractéristiques inconnus du projet sont laissés de côté.
    """
    emp = _source(conn_comptes, registre, projet, source)
    lignes = _lire(emp.base, "SELECT * FROM composant WHERE id = ? AND archive = 0", (identifiant,))
    if not lignes:
        raise Introuvable(f"Composant « {identifiant} » introuvable dans le projet « {source} ».")
    origine = lignes[0]
    repris = {champ: origine[champ] for champ in CHAMPS_REPRIS}
    connu = db.fetch_one(
        conn,
        "SELECT 1 FROM fournisseur WHERE nom = ? AND archive = 0",
        (origine["fournisseur_nom"],),
    )
    if connu is None:
        repris["fournisseur_nom"] = None
    actifs = {a["code"] for a in attributs.list_attributs(conn, actifs_seulement=True)}
    lecture = db.connect(emp.base, creer=False)
    try:
        valeurs = attributs.get_valeurs(lecture, identifiant)
    finally:
        lecture.close()
    fiches = _lire(
        emp.base,
        "SELECT nom_origine, taille FROM document WHERE composant_id = ? AND archive = 0"
        " AND type_document = ? ORDER BY id",
        (identifiant, FICHE_TECHNIQUE),
    )
    return {
        "projet": source,
        "id": identifiant,
        "equipe": _equipe(conn_comptes, source),
        "composant": repris,
        "attributs": {code: v for code, v in valeurs.items() if code in actifs},
        "date_prix": _date_prix(emp.base, identifiant, origine["cree_le"]),
        "fiches": fiches,
    }


def _dans_la_transaction(_conn: sqlite3.Connection) -> nullcontext:
    """Les fiches s'écrivent dans la transaction de la création, pas dans la leur."""
    return nullcontext()


def _fiches(emp: EmplacementsProjet, identifiant: str) -> list[tuple[str, bytes, str | None]]:
    """Fichiers des fiches techniques du composant source ; un fichier absent est sauté,
    un fichier joint deux fois n'est repris qu'une fois."""
    fiches, vus = [], set()
    for doc in _lire(
        emp.base,
        "SELECT nom_origine, chemin, commentaire FROM document WHERE composant_id = ?"
        " AND archive = 0 AND type_document = ? ORDER BY id",
        (identifiant, FICHE_TECHNIQUE),
    ):
        chemin = emp.documents / doc["chemin"]
        try:
            contenu = chemin.read_bytes()
        except OSError as erreur:
            journal_log.warning("Fiche technique illisible, non reprise (%s) : %s", chemin, erreur)
            continue
        if contenu not in vus:
            vus.add(contenu)
            fiches.append((doc["nom_origine"], contenu, doc["commentaire"]))
    return fiches


def create_avec_reprise(
    conn: sqlite3.Connection,
    conn_comptes: sqlite3.Connection,
    registre: Registre,
    cible: EmplacementsProjet,
    valeurs: dict[str, Any],
    reprise: dict[str, str],
) -> dict:
    """Crée le composant saisi et y recopie les fiches techniques du composant repris.

    Le serveur revérifie le dossier et son option : une reprise ne passe pas par l'écran
    seul. Tout ou rien : un fichier refusé annule la création, et les fichiers déjà écrits
    sont retirés.
    """
    source = _source(conn_comptes, registre, cible.code, reprise["projet"])
    if not _lire(
        source.base, "SELECT 1 FROM composant WHERE id = ? AND archive = 0", (reprise["id"],)
    ):
        raise Introuvable(f"Composant « {reprise['id']} » introuvable dans le dossier.")
    fiches = _fiches(source, reprise["id"])
    equipe = _equipe(conn_comptes, reprise["projet"])
    # Dossier des documents du nouveau composant et fichiers qu'il portait déjà : en cas
    # d'échec, seuls les fichiers apparus pendant la création sont retirés.
    deja: dict[Path, set[Path]] = {}

    def joindre(identifiant: str) -> None:
        dossier = cible.documents / "composants" / documents.nom_sur(identifiant)
        deja[dossier] = set(dossier.rglob("*")) if dossier.exists() else set()
        journal.write_journal(
            conn, "composant", identifiant, "reprise", None, f"reprise du dossier ({equipe})"
        )
        for nom, contenu, commentaire in fiches:
            meta = {
                "composant_id": identifiant,
                "type_document": FICHE_TECHNIQUE,
                "commentaire": commentaire,
            }
            documents.add_document(
                conn, cible.documents, (nom, contenu), meta, transaction=_dans_la_transaction
            )

    try:
        return composants.create_composant(conn, valeurs, apres=joindre)
    except BaseException:
        for dossier, avant in deja.items():
            if dossier.exists():
                for chemin in set(dossier.rglob("*")) - avant:
                    if chemin.is_file():
                        chemin.unlink()
        raise
