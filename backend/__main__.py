"""Lancement du serveur : `python -m backend`.

L'adresse et le port viennent de config (NOMENTRACE_HOTE, NOMENTRACE_PORT), comme les
chemins des données : une seule manière de régler une instance, par l'environnement.
"""

import uvicorn

from backend import config


def main() -> None:
    """Démarre Uvicorn sur l'adresse et le port configurés, en un seul processus."""
    uvicorn.run("backend.main:app", host=config.HOTE, port=config.PORT)


if __name__ == "__main__":
    main()
