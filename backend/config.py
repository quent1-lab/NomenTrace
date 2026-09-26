"""Chemins et constantes de Nomentrace, surchargeables par variables d'environnement."""

import os
from pathlib import Path

RACINE: Path = Path(__file__).resolve().parent.parent


def _chemin(variable: str, defaut: Path) -> Path:
    """Renvoie le chemin lu dans la variable d'environnement, ou la valeur par défaut."""
    valeur = os.environ.get(variable)
    return Path(valeur) if valeur else defaut


DOSSIER_DATA: Path = _chemin("NOMENTRACE_DATA", RACINE / "data")
CHEMIN_BASE: Path = _chemin("NOMENTRACE_BASE", DOSSIER_DATA / "nomentrace.db")
DOSSIER_ECHANGE: Path = _chemin("NOMENTRACE_ECHANGE", RACINE / "echange")
DOSSIER_EXPORTS: Path = DOSSIER_ECHANGE / "exports"
DOSSIER_IMPORTS: Path = DOSSIER_ECHANGE / "imports"
DOSSIER_MODELES: Path = DOSSIER_ECHANGE / "modeles"
DOSSIER_SAUVEGARDES: Path = DOSSIER_ECHANGE / "sauvegardes"
DOSSIER_MIGRATIONS: Path = RACINE / "backend" / "migrations"
DOSSIER_MIGRATIONS_COMPTES: Path = RACINE / "backend" / "migrations_comptes"
DOSSIER_STATIC: Path = RACINE / "static"


def lire_port(valeur: str | None, defaut: int = 8000) -> int:
    """Port d'écoute lu dans l'environnement ; refuse clairement une valeur illisible."""
    if not valeur:
        return defaut
    if not valeur.strip().isdigit() or not 1 <= int(valeur) <= 65535:
        raise ValueError(
            f"NOMENTRACE_PORT doit être un entier entre 1 et 65535 (lu : « {valeur} »)."
        )
    return int(valeur)


def lire_concurrence(valeur: str | None, defaut: int = 100) -> int:
    """Nombre maximal de connexions simultanées ; refuse clairement une valeur illisible."""
    if not valeur:
        return defaut
    if not valeur.strip().isdigit() or int(valeur) < 1:
        raise ValueError(f"NOMENTRACE_CONCURRENCE doit être un entier positif (lu : « {valeur} »).")
    return int(valeur)


# Adresse et port d'écoute, lus par `python -m backend` (backend/__main__.py).
HOTE: str = os.environ.get("NOMENTRACE_HOTE") or "127.0.0.1"
PORT: int = lire_port(os.environ.get("NOMENTRACE_PORT"))
# Au-delà, Uvicorn répond 503 aussitôt plutôt que d'empiler les requêtes.
CONCURRENCE_MAX: int = lire_concurrence(os.environ.get("NOMENTRACE_CONCURRENCE"))

# Comptes : base distincte de celle du projet, partagée un jour par plusieurs projets. Chaque
# instance sert un projet, désigné par un code stable (le nom du projet, lui, peut changer).
CHEMIN_COMPTES: Path = _chemin("NOMENTRACE_COMPTES", DOSSIER_DATA / "comptes.db")
CODE_PROJET: str = os.environ.get("NOMENTRACE_PROJET") or "principal"


def lire_booleen(valeur: str | None) -> bool:
    """Vrai pour « 1 », « oui », « true » ou « vrai » (casse ignorée), faux sinon."""
    return (valeur or "").strip().lower() in {"1", "oui", "true", "vrai"}


# Mode local : aucun compte, un administrateur implicite, écoute sur la boucle locale seulement.
# Il doit être demandé explicitement (lancer.bat le fait) : sans lui, la connexion est exigée.
MODE_LOCAL: bool = lire_booleen(os.environ.get("NOMENTRACE_MODE_LOCAL"))
HOTES_LOCAUX: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})

# Adresse publique de l'instance, utilisée seulement pour écrire les liens d'invitation
# affichés en ligne de commande.
URL_PUBLIQUE: str | None = os.environ.get("NOMENTRACE_URL") or None

FORMAT_LOG: str = "%(asctime)s %(levelname)s %(name)s : %(message)s"
