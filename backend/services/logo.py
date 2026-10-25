"""Logo de l'établissement : une image PNG ou JPEG, placée en tête des demandes de devis."""

import io
import logging
import sqlite3
from datetime import datetime

from PIL import Image, UnidentifiedImageError

from backend import db
from backend.erreurs import ErreurMetier, Introuvable
from backend.services import journal

journal_log = logging.getLogger(__name__)

TAILLE_MAX: int = 2 * 1024 * 1024
FORMATS: dict[str, str] = {"PNG": "image/png", "JPEG": "image/jpeg"}
# Au-delà, l'image est refusée : un logo n'a pas besoin de plus et le PDF grossirait.
COTE_MAX: int = 4000


def get_logo(conn: sqlite3.Connection) -> dict | None:
    """Le logo (type, contenu, dimensions en pixels), ou None s'il n'y en a pas."""
    return db.fetch_one(conn, "SELECT * FROM logo WHERE id = 1")


def lire_image(contenu: bytes) -> tuple[str, int, int]:
    """Vérifie que le fichier est une image PNG ou JPEG lisible : (type, largeur, hauteur)."""
    if not contenu:
        raise ErreurMetier("Fichier vide.")
    if len(contenu) > TAILLE_MAX:
        raise ErreurMetier("Logo trop lourd : 2 Mo au plus.")
    try:
        # Seuls les décodeurs PNG et JPEG sont essayés : un envoi n'atteint pas les autres
        # formats de Pillow, d'où viennent la plupart de ses failles.
        with Image.open(io.BytesIO(contenu), formats=list(FORMATS)) as image:
            image.verify()
            format_image, (largeur, hauteur) = image.format, image.size
    except (UnidentifiedImageError, OSError, SyntaxError) as erreur:
        journal_log.info("Logo refusé, image illisible : %s", erreur)
        raise ErreurMetier("Ce fichier n'est pas une image PNG ou JPEG lisible.") from erreur
    if format_image not in FORMATS:
        raise ErreurMetier("Le logo doit être une image PNG ou JPEG.")
    if max(largeur, hauteur) > COTE_MAX:
        raise ErreurMetier(f"Image trop grande : {COTE_MAX} pixels de côté au plus.")
    return FORMATS[format_image], largeur, hauteur


def set_logo(conn: sqlite3.Connection, contenu: bytes) -> dict:
    """Enregistre le logo, en remplaçant le précédent, avec une ligne de journal."""
    type_mime, largeur, hauteur = lire_image(contenu)
    maintenant = datetime.now().isoformat(timespec="seconds")
    with db.transaction(conn):
        ancien = get_logo(conn)
        conn.execute(
            "INSERT INTO logo (id, type_mime, contenu, largeur, hauteur, modifie_le)"
            " VALUES (1, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
            " type_mime = excluded.type_mime, contenu = excluded.contenu,"
            " largeur = excluded.largeur, hauteur = excluded.hauteur,"
            " modifie_le = excluded.modifie_le",
            (type_mime, contenu, largeur, hauteur, maintenant),
        )
        journal.write_journal(
            conn,
            "parametre",
            "logo",
            "logo",
            "remplacé" if ancien else None,
            f"{largeur} × {hauteur} px",
        )
    return {"type_mime": type_mime, "largeur": largeur, "hauteur": hauteur}


def delete_logo(conn: sqlite3.Connection) -> None:
    """Retire le logo ; les demandes de devis n'en portent plus."""
    with db.transaction(conn):
        if get_logo(conn) is None:
            raise Introuvable("Aucun logo enregistré.")
        conn.execute("DELETE FROM logo WHERE id = 1")
        journal.write_journal(conn, "parametre", "logo", "logo", "présent", None)
