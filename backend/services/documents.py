"""Documents joints aux commandes et aux composants.

Les fichiers sont rangés dans le dossier d'échange (echange/documents/commandes/CMD-001/…,
echange/documents/composants/<id>/…) pour rester accessibles depuis l'explorateur ; la base
garde leur chemin relatif, leur taille et leur empreinte SHA-256.
"""

import hashlib
import mimetypes
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import commandes, composants, journal

TAILLE_MAX: int = 20 * 1024 * 1024
EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif",
        ".xlsx", ".xls", ".ods", ".csv", ".docx", ".doc", ".odt", ".txt",
        ".eml", ".msg", ".step", ".stp", ".dxf",
    }
)  # fmt: skip
# Types ouverts directement dans le navigateur ; les autres sont téléchargés.
TYPES_EN_LIGNE: frozenset[str] = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/gif", "text/plain"}
)
TYPES_DOCUMENT: tuple[str, ...] = (
    "Devis", "Bon de commande", "Facture", "Bon de livraison",
    "Fiche technique", "Plan", "Photo", "Autre",
)  # fmt: skip


def _nom_sur(nom: str) -> str:
    """Nom de fichier sans chemin, sans accents ni caractères spéciaux."""
    base = Path(nom.replace("\\", "/")).name
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base[:120] or "document"


def _check_fichier(nom: str, contenu: bytes) -> str:
    """Contrôle extension et taille ; renvoie l'extension en minuscules."""
    extension = Path(nom).suffix.lower()
    if extension not in EXTENSIONS:
        autorises = ", ".join(sorted(e.lstrip(".") for e in EXTENSIONS))
        raise ErreurMetier(
            f"Type de fichier non accepté : « {extension or nom} ». Acceptés : {autorises}."
        )
    if not contenu:
        raise ErreurMetier(f"Le fichier « {nom} » est vide.")
    if len(contenu) > TAILLE_MAX:
        raise ErreurMetier(f"Le fichier « {nom} » dépasse {TAILLE_MAX // (1024 * 1024)} Mo.")
    return extension


def _chemin_libre(dossier: Path, relatif_dossier: Path, nom: str) -> Path:
    """Chemin relatif libre dans le dossier cible : suffixe -2, -3… si le nom est pris."""
    cible = relatif_dossier / nom
    rang = 2
    while (dossier / cible).exists():
        cible = relatif_dossier / f"{Path(nom).stem}-{rang}{Path(nom).suffix}"
        rang += 1
    return cible


def ensure_cible(conn: sqlite3.Connection, commande: str | None, composant: str | None) -> Path:
    """Vérifie la cible du rattachement et renvoie son sous-dossier."""
    if commande is not None:
        commandes.get_commande(conn, commande)
        return Path("commandes") / _nom_sur(commande)
    if composant is None:
        raise ErreurMetier("Un document se rattache à une commande ou à un composant.")
    composants.get_composant(conn, composant)
    return Path("composants") / _nom_sur(composant)


def add_document(
    conn: sqlite3.Connection,
    dossier: Path,
    fichier: tuple[str, bytes],
    meta: dict[str, Any],
) -> dict:
    """Enregistre un fichier et sa fiche. `meta` porte la cible, le type et le commentaire."""
    nom, contenu = fichier
    _check_fichier(nom, contenu)
    if meta["type_document"] not in TYPES_DOCUMENT:
        raise ErreurMetier(f"Type de document inconnu : « {meta['type_document']} ».")
    empreinte = hashlib.sha256(contenu).hexdigest()
    commande, composant = meta.get("commande_numero"), meta.get("composant_id")
    with db.transaction(conn, immediate=True):
        sous_dossier = ensure_cible(conn, commande, composant)
        doublon = db.fetch_one(
            conn,
            "SELECT nom_origine FROM document WHERE archive = 0 AND empreinte = ?"
            " AND commande_numero IS ? AND composant_id IS ?",
            (empreinte, commande, composant),
        )
        if doublon:
            raise Conflit(f"Ce fichier est déjà joint (sous le nom « {doublon['nom_origine']} »).")
        relatif = _chemin_libre(dossier, sous_dossier, _nom_sur(nom))
        (dossier / relatif).parent.mkdir(parents=True, exist_ok=True)
        (dossier / relatif).write_bytes(contenu)
        identifiant = _insert_fiche(
            conn,
            dossier / relatif,
            {
                "commande_numero": commande,
                "composant_id": composant,
                "type_document": meta["type_document"],
                "nom_origine": Path(nom.replace("\\", "/")).name,
                "chemin": relatif.as_posix(),
                "type_mime": mimetypes.guess_type(nom)[0],
                "taille": len(contenu),
                "empreinte": empreinte,
                "commentaire": meta.get("commentaire"),
            },
        )
        cle = commande or composant
        table = "commande" if commande else "composant"
        journal.write_journal(conn, table, cle, f"document {identifiant}", None, nom)
    return get_document(conn, identifiant)


def _insert_fiche(conn: sqlite3.Connection, fichier: Path, valeurs: dict[str, Any]) -> int:
    """Insère la fiche du document ; en cas d'échec, le fichier déjà écrit est retiré."""
    try:
        return db.insert_row(conn, "document", valeurs)
    except sqlite3.Error:
        fichier.unlink(missing_ok=True)
        raise


def get_document(conn: sqlite3.Connection, identifiant: int) -> dict:
    document = db.fetch_one(
        conn, "SELECT * FROM document WHERE id = ? AND archive = 0", (identifiant,)
    )
    if document is None:
        raise Introuvable(f"Document {identifiant} introuvable ou retiré.")
    return document


def list_documents_commande(conn: sqlite3.Connection, numero: str) -> list[dict]:
    commandes.get_commande(conn, numero)
    return db.fetch_all(
        conn,
        "SELECT * FROM document WHERE commande_numero = ? AND archive = 0 ORDER BY ajoute_le, id",
        (numero,),
    )


def list_documents_composant(conn: sqlite3.Connection, identifiant: str) -> list[dict]:
    """Documents du composant et documents des commandes où il figure."""
    composants.get_composant(conn, identifiant)
    return db.fetch_all(
        conn,
        "SELECT * FROM v_document_composant WHERE pour_composant = ?"
        " ORDER BY source DESC, ajoute_le, id",
        (identifiant,),
    )


def get_fichier(conn: sqlite3.Connection, dossier: Path, identifiant: int) -> dict:
    """Chemin absolu du fichier, son nom d'origine et le mode d'ouverture."""
    document = get_document(conn, identifiant)
    chemin = (dossier / document["chemin"]).resolve()
    if not chemin.is_relative_to(dossier.resolve()) or not chemin.is_file():
        raise Introuvable(
            f"Le fichier de « {document['nom_origine']} » est absent du dossier des documents."
        )
    en_ligne = document["type_mime"] in TYPES_EN_LIGNE
    return {"chemin": chemin, "nom": document["nom_origine"], "type_mime": document["type_mime"],
            "en_ligne": en_ligne}  # fmt: skip


def patch_document(conn: sqlite3.Connection, identifiant: int, modifs: dict[str, Any]) -> dict:
    if "type_document" in modifs and modifs["type_document"] not in TYPES_DOCUMENT:
        raise ErreurMetier(f"Type de document inconnu : « {modifs['type_document']} ».")
    with db.transaction(conn):
        get_document(conn, identifiant)
        journal.update_with_journal(
            conn, "document", identifiant, modifs, frozenset({"type_document", "commentaire"})
        )
    return get_document(conn, identifiant)


def archive_document(conn: sqlite3.Connection, identifiant: int) -> None:
    """Retire un document des listes ; le fichier reste dans le dossier des documents."""
    with db.transaction(conn):
        get_document(conn, identifiant)
        journal.update_with_journal(
            conn, "document", identifiant, {"archive": 1}, frozenset({"archive"})
        )
