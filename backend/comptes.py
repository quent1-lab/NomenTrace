"""Gestion des comptes en ligne de commande : `python -m backend.comptes creer-admin ADRESSE`.

Sert à créer le premier administrateur d'une instance, et de secours si plus personne ne
peut entrer : la commande crée le compte ou lui rend le rôle d'administrateur, puis affiche
un lien d'invitation neuf (72 h, usage unique) pour choisir un mot de passe. Elle s'exécute
sur le serveur, avec les mêmes variables d'environnement que l'application.
"""

import argparse
import logging
import sys

from backend import config, db
from backend.erreurs import ErreurMetier
from backend.services import comptes


def lien_invitation(jeton: str, base: str | None) -> str:
    """Adresse de la page qui accueille l'invitation.

    Le jeton est placé après « # » : le navigateur ne l'envoie jamais au serveur, il
    n'apparaît donc ni dans les journaux d'accès ni dans un en-tête Referer.
    """
    racine = (base or f"http://127.0.0.1:{config.PORT}").rstrip("/")
    return f"{racine}/connexion.html#invitation={jeton}"


def creer_admin(identifiant: str, nom: str | None) -> int:
    comptes.prepare_base(config.CHEMIN_COMPTES)
    conn = db.connect(config.CHEMIN_COMPTES)
    try:
        resultat = comptes.ensure_admin(
            conn, config.CODE_PROJET, identifiant, nom or identifiant.split("@")[0]
        )
    except ErreurMetier as erreur:
        print(f"Erreur : {erreur.message}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    utilisateur = resultat["utilisateur"]
    print(f"Administrateur « {utilisateur['nom']} » ({utilisateur['identifiant']}),")
    print(f"projet « {config.CODE_PROJET} ». Lien pour choisir le mot de passe,")
    print(f"valable jusqu'au {resultat['expire_le'].replace('T', ' à ')} :")
    print()
    print(lien_invitation(resultat["jeton"], config.URL_PUBLIQUE))
    print()
    print("Ce lien donne accès au compte : le transmettre par un canal sûr.")
    return 0


def main(arguments: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format=config.FORMAT_LOG)
    analyseur = argparse.ArgumentParser(prog="python -m backend.comptes", description=__doc__)
    commandes = analyseur.add_subparsers(dest="commande", required=True)
    admin = commandes.add_parser(
        "creer-admin", help="créer ou rétablir un administrateur et afficher son lien"
    )
    admin.add_argument("identifiant", help="adresse mail servant d'identifiant")
    admin.add_argument("--nom", help="nom affiché (par défaut, le début de l'adresse)")
    lus = analyseur.parse_args(arguments)
    return creer_admin(lus.identifiant, lus.nom)


if __name__ == "__main__":
    sys.exit(main())
