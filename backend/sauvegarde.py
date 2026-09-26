"""Sauvegarde et restauration en ligne de commande, sur le serveur.

    python -m backend.sauvegarde archive FICHIER.zip
    python -m backend.sauvegarde restaurer FICHIER.zip

`archive` écrit l'archive complète : base du projet, base des comptes et documents,
corbeille comprise. C'est ce que la sauvegarde nocturne chiffre et envoie hors du serveur
(deploiement/sauvegarde_distante.sh). `restaurer` remet une telle archive en place,
application arrêtée. Les deux commandes s'exécutent avec les mêmes variables
d'environnement que l'application.
"""

import argparse
import logging
import os
import shutil
import socket
import sys
from pathlib import Path

from backend import config
from backend.erreurs import ErreurMetier
from backend.services import restauration, sauvegardes


def dossier_documents() -> Path:
    return config.DOSSIER_ECHANGE / "documents"


def serveur_actif(hote: str, port: int) -> bool:
    """Vrai si un serveur répond sur l'adresse et le port de l'application."""
    with socket.socket() as sonde:
        sonde.settimeout(1)
        return sonde.connect_ex((hote, port)) == 0


def creer_archive(cible: Path) -> int:
    temporaire = sauvegardes.build_archive(
        config.CHEMIN_BASE, dossier_documents(), config.CHEMIN_COMPTES
    )
    cible.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(temporaire, cible)
    # L'archive contient les empreintes des mots de passe : lisible par son seul propriétaire.
    os.chmod(cible, 0o600)
    print(cible)
    return 0


def restaurer(archive: Path, avec_documents: bool) -> int:
    if serveur_actif(config.HOTE, config.PORT):
        print(
            f"Erreur : Nomentrace répond sur {config.HOTE}:{config.PORT}. Arrêter le service"
            " avant de restaurer (sudo systemctl stop nomentrace).",
            file=sys.stderr,
        )
        return 1
    try:
        resultat = restauration.restore_archive(
            archive,
            config.CHEMIN_BASE,
            config.CHEMIN_COMPTES,
            config.DOSSIER_SAUVEGARDES,
            dossier_documents(),
            avec_documents,
        )
    except ErreurMetier as erreur:
        print(f"Erreur : {erreur.message}", file=sys.stderr)
        return 1
    print(f"Base du projet restaurée (schéma {resultat['version_schema']}).")
    print(f"  état précédent sauvegardé : {resultat['securite_base'] or 'aucun'}")
    if resultat["comptes"]:
        print("Base des comptes restaurée.")
        print(f"  état précédent sauvegardé : {resultat['securite_comptes'] or 'aucun'}")
    else:
        print("L'archive ne contient pas de base des comptes : celle en place est gardée.")
    if avec_documents:
        print("Documents restaurés.")
        if resultat["documents_mis_de_cote"]:
            print(f"  documents précédents mis de côté : {resultat['documents_mis_de_cote']}")
    print("Les mises à jour de schéma manquantes s'appliqueront au démarrage du service.")
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
    lus = analyseur.parse_args(arguments)
    if lus.commande == "archive":
        return creer_archive(lus.fichier)
    return restaurer(lus.fichier, not lus.sans_documents)


if __name__ == "__main__":
    sys.exit(main())
