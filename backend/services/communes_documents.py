"""Documents d'une commande commune (phase 16b) : devis, bon de commande, facture…

Un document déposé depuis la page du dossier est joint à la copie de chaque projet présent,
dans le dossier des documents de ce projet : il s'y consulte avec la copie et depuis la fiche
de chacun de ses composants, sans rien changer aux vues du projet. La page de la commune le
montre une seule fois (même empreinte, même type). Un projet qui rejoint la commune reçoit
les documents déjà déposés. Le retirer l'archive dans toutes les copies ; aucun fichier
n'est effacé.
"""

import logging
from pathlib import Path
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import communes_sync, documents
from backend.services.communes_sync import Emplacements

journal_log = logging.getLogger(__name__)


def _documents_copie(base: Path, numero_local: str) -> list[dict]:
    conn = db.connect(base, creer=False)
    try:
        return db.fetch_all(
            conn,
            "SELECT * FROM document WHERE commande_numero = ? AND archive = 0"
            " ORDER BY ajoute_le, id",
            (numero_local,),
        )
    finally:
        conn.close()


def lister(emp: Emplacements, participants: dict[str, str]) -> list[dict]:
    """Documents de la commune, une fois chacun, avec les copies qui le portent."""
    regroupes: dict[tuple[str, str], dict] = {}
    for projet, numero_local in participants.items():
        if projet not in emp.projets:
            continue
        for d in _documents_copie(emp.projets[projet], numero_local):
            cle = (d["empreinte"], d["type_document"])
            entree = regroupes.setdefault(
                cle,
                {
                    "empreinte": d["empreinte"],
                    "type_document": d["type_document"],
                    "nom_origine": d["nom_origine"],
                    "taille": d["taille"],
                    "commentaire": d["commentaire"],
                    "ajoute_le": d["ajoute_le"],
                    "copies": [],
                },
            )
            entree["copies"].append({"projet": projet, "id": d["id"]})
    return sorted(regroupes.values(), key=lambda d: (d["ajoute_le"], d["nom_origine"]))


def _joindre(
    emp: Emplacements,
    auteur: str | None,
    cible: tuple[str, str],
    fichier: tuple[str, bytes],
    meta: dict[str, Any],
) -> bool:
    """Joint un fichier à la copie d'un projet ; False s'il y est déjà."""
    projet, numero_local = cible
    conn = db.connect(emp.projets[projet], auteur, creer=False)
    try:
        documents.add_document(
            conn,
            emp.documents[projet],
            fichier,
            {**meta, "commande_numero": numero_local},
            transaction=communes_sync.ouverte,
        )
        return True
    except Conflit:
        return False
    finally:
        conn.close()


def deposer(
    emp: Emplacements,
    participants: dict[str, str],
    auteur: str | None,
    depot: tuple[list[tuple[str, bytes]], dict[str, Any]],
) -> dict:
    """Joint chaque fichier à toutes les copies ; un refus n'empêche pas les autres.
    `participants` : tous en ligne (communes.contexte_documents)."""
    fichiers, meta = depot
    joints, erreurs = 0, []
    for fichier in fichiers:
        try:
            for projet, numero_local in participants.items():
                joints += _joindre(emp, auteur, (projet, numero_local), fichier, meta)
        except ErreurMetier as erreur:
            journal_log.info("Document refusé (%s) : %s", fichier[0], erreur.message)
            erreurs.append(erreur.message)
    if erreurs and not joints:
        raise ErreurMetier(" ".join(erreurs))
    return {"documents": lister(emp, participants), "erreurs": erreurs}


def retirer(
    emp: Emplacements, participants: dict[str, str], auteur: str | None, empreinte: str
) -> dict:
    """Archive le document dans toutes les copies ; le fichier reste dans chaque projet."""
    retires = 0
    for projet, numero_local in participants.items():
        base = db.connect(emp.projets[projet], auteur, creer=False)
        try:
            for d in _documents_copie(emp.projets[projet], numero_local):
                if d["empreinte"] == empreinte:
                    documents.archive_document(base, d["id"], transaction=communes_sync.ouverte)
                    retires += 1
        finally:
            base.close()
    if not retires:
        raise Introuvable("Document introuvable dans cette commande.")
    return {"documents": lister(emp, participants)}


def recopier(
    emp: Emplacements, participants: dict[str, str], projet: str, auteur: str | None
) -> int:
    """Un projet rejoint la commune : il reçoit les documents déjà joints aux autres copies."""
    autres = {p: n for p, n in participants.items() if p != projet}
    recus = 0
    for d in lister(emp, autres):
        source = d["copies"][0]
        fiche = _documents_copie(emp.projets[source["projet"]], autres[source["projet"]])
        chemin = next(f["chemin"] for f in fiche if f["id"] == source["id"])
        contenu = (emp.documents[source["projet"]] / chemin).read_bytes()
        meta = {"type_document": d["type_document"], "commentaire": d["commentaire"]}
        recus += _joindre(
            emp, auteur, (projet, participants[projet]), (d["nom_origine"], contenu), meta
        )
    return recus


def fichier(emp: Emplacements, participants: dict[str, str], projet: str, identifiant: int) -> dict:
    """Le fichier d'un document de la commune, lu dans la copie d'un de ses projets."""
    numero_local = participants.get(projet)
    if numero_local is None or projet not in emp.projets:
        raise Introuvable("Document introuvable dans cette commande.")
    if not any(d["id"] == identifiant for d in _documents_copie(emp.projets[projet], numero_local)):
        raise Introuvable("Document introuvable dans cette commande.")
    lecture = db.connect(emp.projets[projet], creer=False)
    try:
        return documents.get_fichier(lecture, emp.documents[projet], identifiant)
    finally:
        lecture.close()
