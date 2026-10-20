"""Sauvegarde et restauration en ligne de commande, sur le serveur.

    python -m backend.sauvegarde archive FICHIER.zip
    python -m backend.sauvegarde restaurer FICHIER.zip [--sans-documents] [--projet CODE]

`archive` écrit l'archive complète du serveur : base commune (comptes et registre des
projets), puis base et documents, corbeille comprise, de chaque projet inscrit. C'est ce
que la sauvegarde nocturne chiffre et envoie hors du serveur
(deploiement/sauvegarde_distante.sh). `restaurer` remet une telle archive en place,
application arrêtée ; une archive d'un seul projet (format d'avant la phase 15a-2) va au
projet de l'instance, ou à celui de `--projet`. Les deux commandes s'exécutent avec les
mêmes variables d'environnement que l'application.
"""

import argparse
import logging
import os
import shutil
import socket
import sys
from pathlib import Path

from backend import config, db
from backend.erreurs import ErreurMetier
from backend.services import comptes, projets, restauration, sauvegardes


def serveur_actif(hote: str, port: int) -> bool:
    """Vrai si un serveur répond sur l'adresse et le port de l'application."""
    with socket.socket() as sonde:
        sonde.settimeout(1)
        return sonde.connect_ex((hote, port)) == 0


def _projets_inscrits() -> list[tuple[str, Path, Path]]:
    """Code, base et documents de chaque projet inscrit dont la base existe."""
    comptes.prepare_base(config.CHEMIN_COMPTES)
    conn = db.connect(config.CHEMIN_COMPTES)
    try:
        codes = projets.list_codes(conn)
    finally:
        conn.close()
    resultat = []
    for code in codes:
        emp = projets.emplacements(config.DOSSIER_DATA, config.DOSSIER_ECHANGE, code)
        if emp.base.is_file():
            resultat.append((code, emp.base, emp.documents))
        else:
            print(f"Attention : projet « {code} » sans base ({emp.base}), ignoré.", file=sys.stderr)
    return resultat


def creer_archive(cible: Path) -> int:
    temporaire = sauvegardes.build_archive_serveur(config.CHEMIN_COMPTES, _projets_inscrits())
    cible.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(temporaire, cible)
    # L'archive contient les empreintes des mots de passe : lisible par son seul propriétaire.
    os.chmod(cible, 0o600)
    print(cible)
    return 0


def _afficher(resultat: dict, avec_documents: bool) -> None:
    if resultat["comptes"]:
        print("Base commune (comptes et projets) restaurée.")
        print(f"  état précédent sauvegardé : {resultat['securite_comptes'] or 'aucun'}")
    else:
        print("L'archive ne contient pas de base des comptes : celle en place est gardée.")
    for code, projet in resultat["projets"].items():
        print(f"Projet « {code} » restauré (schéma {projet['version_schema']}).")
        print(f"  état précédent sauvegardé : {projet['securite_base'] or 'aucun'}")
        if avec_documents and projet["documents_mis_de_cote"]:
            print(f"  documents précédents mis de côté : {projet['documents_mis_de_cote']}")
    print("Les mises à jour de schéma manquantes s'appliqueront au démarrage du service.")


def restaurer(archive: Path, avec_documents: bool, projet: str | None) -> int:
    if serveur_actif(config.HOTE, config.PORT):
        print(
            f"Erreur : Nomentrace répond sur {config.HOTE}:{config.PORT}. Arrêter le service"
            " avant de restaurer (sudo systemctl stop nomentrace).",
            file=sys.stderr,
        )
        return 1
    cible = restauration.Cible(
        config.CHEMIN_COMPTES,
        config.DOSSIER_DATA,
        config.DOSSIER_ECHANGE,
        config.CHEMIN_ANCIENNE_BASE,
    )
    try:
        resultat = restauration.restore_archive(
            archive, cible, projet or config.CODE_PROJET, avec_documents
        )
    except ErreurMetier as erreur:
        print(f"Erreur : {erreur.message}", file=sys.stderr)
        return 1
    _afficher(resultat, avec_documents)
    return 0


def main(arguments: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format=config.FORMAT_LOG)
    analyseur = argparse.ArgumentParser(
        prog="python -m backend.sauvegarde",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commandes = analyseur.add_subparsers(dest="commande", required=True)
    archive = commandes.add_parser("archive", help="écrire l'archive complète dans FICHIER")
    archive.add_argument("fichier", type=Path)
    restauration_ = commandes.add_parser("restaurer", help="remettre en place une archive")
    restauration_.add_argument("fichier", type=Path)
    restauration_.add_argument(
        "--sans-documents", action="store_true", help="ne restaurer que les bases"
    )
    restauration_.add_argument(
        "--projet", help="projet qui reçoit une archive d'un seul projet (défaut : l'instance)"
    )
    lus = analyseur.parse_args(arguments)
    if lus.commande == "archive":
        return creer_archive(lus.fichier)
    return restaurer(lus.fichier, not lus.sans_documents, lus.projet)


if __name__ == "__main__":
    sys.exit(main())
