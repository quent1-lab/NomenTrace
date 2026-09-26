"""Lancement du serveur : `python -m backend`.

L'adresse et le port viennent de config (NOMENTRACE_HOTE, NOMENTRACE_PORT), comme les
chemins des données : une seule manière de régler une instance, par l'environnement.
"""

import sys

import uvicorn

from backend import config


def check_configuration(hote: str, mode_local: bool) -> str | None:
    """Motif de refus de démarrer, ou None si la configuration est sûre.

    Le mode local, sans connexion, n'écoute que la boucle locale : sur une autre adresse,
    n'importe quel poste du réseau entrerait en administrateur.
    """
    if mode_local and hote not in config.HOTES_LOCAUX:
        return (
            f"Refus de démarrer : le mode local (sans connexion) ne peut écouter que 127.0.0.1,"
            f" pas « {hote} ». Retirer NOMENTRACE_MODE_LOCAL pour exiger la connexion, ou"
            " écouter sur 127.0.0.1."
        )
    return None


def options_uvicorn(hote: str, port: int, mode_local: bool, concurrence: int) -> dict:
    """Options de lancement d'Uvicorn.

    En mode connecté, l'outil est servi derrière un proxy (Caddy) sur la même machine :
    l'adresse du visiteur et le schéma (https) ne sont lus dans les en-têtes X-Forwarded-*
    que si la requête vient de 127.0.0.1, jamais d'ailleurs. En mode local, aucun proxy
    n'est attendu et ces en-têtes sont ignorés.
    """
    return {
        "host": hote,
        "port": port,
        # Pas d'en-tête « server » : inutile de dire à un visiteur quel serveur répond.
        "server_header": False,
        "proxy_headers": not mode_local,
        "forwarded_allow_ips": "127.0.0.1",
        "limit_concurrency": concurrence,
    }


def main() -> None:
    """Démarre Uvicorn sur l'adresse et le port configurés, en un seul processus."""
    refus = check_configuration(config.HOTE, config.MODE_LOCAL)
    if refus:
        sys.exit(refus)
    options = options_uvicorn(config.HOTE, config.PORT, config.MODE_LOCAL, config.CONCURRENCE_MAX)
    uvicorn.run("backend.main:app", **options)


if __name__ == "__main__":
    main()
