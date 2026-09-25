"""Droits d'accès : qui peut appeler quelle route, et sur quels composants.

Chaque route de l'API figure dans la table REGLES avec la condition qu'elle exige. Une route
absente de la table est réservée à l'administrateur : une route ajoutée plus tard ne peut
pas s'ouvrir par oubli. Un test vérifie que toutes les routes y sont déclarées.

Les rôles :
- lecteur : lit tout, télécharge les exports Excel ;
- contributeur : écrit sur les composants des blocs qui lui sont attribués, fait les
  mouvements de stock et les imports (ligne par ligne, dans ses blocs). Deux permissions
  s'ajoutent au cas par cas : « achats » (commandes, réceptions, demandes de devis,
  modification des fournisseurs) et « ensembles » (création et modification de
  l'arborescence). Tout contributeur peut proposer un fournisseur, qui reste « à valider » ;
- administrateur : tout, dont les paramètres, les budgets, les utilisateurs, le nettoyage,
  les sauvegardes et la validation des fournisseurs.
"""

import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field

from backend import db
from backend.erreurs import ErreurMetier, Introuvable

journal_log = logging.getLogger(__name__)

LECTEUR = "lecteur"
CONTRIBUTEUR = "contributeur"
ADMINISTRATEUR = "administrateur"
ROLES: tuple[str, ...] = (LECTEUR, CONTRIBUTEUR, ADMINISTRATEUR)

ACHATS = "achats"
ENSEMBLES = "ensembles"
PERMISSIONS: tuple[str, ...] = (ACHATS, ENSEMBLES)


class AccesRefuse(ErreurMetier):
    """L'utilisateur est connecté mais n'a pas le droit de faire cela."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 403)


class NonConnecte(ErreurMetier):
    def __init__(self) -> None:
        super().__init__("Connexion requise.", 401)


@dataclass(frozen=True)
class Utilisateur:
    """Utilisateur d'une requête, avec ses droits sur le projet de l'instance.

    `role` vaut None si le compte n'a aucun accès à ce projet.
    """

    id: int | None
    identifiant: str
    nom: str
    role: str | None
    blocs: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    local: bool = False

    @property
    def admin(self) -> bool:
        return self.role == ADMINISTRATEUR

    def ecrit(self) -> bool:
        return self.role in (CONTRIBUTEUR, ADMINISTRATEUR)

    def a_permission(self, permission: str) -> bool:
        return self.admin or (self.role == CONTRIBUTEUR and permission in self.permissions)

    def ecrit_bloc(self, bloc: str | None) -> bool:
        return self.admin or (self.role == CONTRIBUTEUR and bloc in self.blocs)

    def description(self) -> dict:
        """Ce que l'interface a besoin de savoir pour masquer ce qui est interdit."""
        return {
            "id": self.id,
            "identifiant": self.identifiant,
            "nom": self.nom,
            "role": self.role,
            "blocs": sorted(self.blocs),
            "permissions": sorted(self.permissions),
            "local": self.local,
        }


UTILISATEUR_LOCAL = Utilisateur(
    id=None, identifiant="local", nom="local", role=ADMINISTRATEUR, local=True
)


# --- Vérifications ------------------------------------------------------------------------------


def exiger_admin(utilisateur: Utilisateur) -> None:
    if not utilisateur.admin:
        raise AccesRefuse("Action réservée à un administrateur.")


def exiger_ecriture(utilisateur: Utilisateur) -> None:
    if not utilisateur.ecrit():
        raise AccesRefuse("Votre rôle de lecteur ne permet pas de modifier les données.")


def exiger_permission(utilisateur: Utilisateur, permission: str) -> None:
    if not utilisateur.a_permission(permission):
        libelle = {ACHATS: "les achats", ENSEMBLES: "les ensembles"}[permission]
        raise AccesRefuse(f"Vous n'avez pas la permission de modifier {libelle}.")


def exiger_bloc(utilisateur: Utilisateur, bloc: str | None) -> None:
    exiger_ecriture(utilisateur)
    if not utilisateur.ecrit_bloc(bloc):
        raise AccesRefuse(
            f"Le bloc « {bloc} » ne vous est pas attribué : ses composants ne sont modifiables"
            " que par ses contributeurs."
        )


def bloc_composant(conn: sqlite3.Connection, identifiant: str) -> str:
    ligne = db.fetch_one(conn, "SELECT bloc_code FROM composant WHERE id = ?", (identifiant,))
    if ligne is None:
        raise Introuvable(f"Composant « {identifiant} » introuvable.")
    return str(ligne["bloc_code"])


def exiger_composant(conn: sqlite3.Connection, utilisateur: Utilisateur, identifiant: str) -> None:
    if not utilisateur.admin:
        exiger_bloc(utilisateur, bloc_composant(conn, identifiant))


def _entier(identifiant: str) -> int:
    try:
        return int(identifiant)
    except ValueError:
        raise Introuvable(f"Identifiant invalide : « {identifiant} ».") from None


def exiger_affectation(
    conn: sqlite3.Connection, utilisateur: Utilisateur, identifiant: str
) -> None:
    if utilisateur.admin:
        return
    ligne = db.fetch_one(
        conn, "SELECT composant_id FROM affectation WHERE id = ?", (_entier(identifiant),)
    )
    if ligne is None:
        raise Introuvable(f"Affectation {identifiant} introuvable.")
    exiger_composant(conn, utilisateur, ligne["composant_id"])


def exiger_document(conn: sqlite3.Connection, utilisateur: Utilisateur, identifiant: str) -> None:
    """Document d'un composant : bloc du composant ; document d'une commande : achats."""
    if utilisateur.admin:
        return
    ligne = db.fetch_one(
        conn,
        "SELECT composant_id, commande_numero FROM document WHERE id = ?",
        (_entier(identifiant),),
    )
    if ligne is None:
        raise Introuvable(f"Document {identifiant} introuvable.")
    if ligne["composant_id"]:
        exiger_composant(conn, utilisateur, ligne["composant_id"])
    else:
        exiger_permission(utilisateur, ACHATS)


CHAMPS_BUDGET: frozenset[str] = frozenset({"budget_cible_ht", "budget_verrouille"})


def exiger_budget(utilisateur: Utilisateur, champs: set[str] | frozenset[str]) -> None:
    """Budgets d'ensemble : l'arbitrage reste à l'administrateur."""
    if champs & CHAMPS_BUDGET and not utilisateur.admin:
        raise AccesRefuse("Les budgets d'ensemble sont réservés à un administrateur.")


def exiger_statut_fournisseur(
    conn: sqlite3.Connection, utilisateur: Utilisateur, nom: str, statut: str | None
) -> None:
    """Valider un fournisseur, ou lui retirer sa validation, revient à l'administrateur."""
    if utilisateur.admin or statut is None:
        return
    actuel = db.fetch_one(conn, "SELECT statut FROM fournisseur WHERE nom = ?", (nom,))
    if actuel is not None and actuel["statut"] != statut:
        raise AccesRefuse("La validation d'un fournisseur est réservée à un administrateur.")


# --- Table des routes ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Regle:
    """Condition d'accès d'une route.

    niveau : 'public' (sans connexion), 'session' (connecté, même sans accès au projet),
    'lecture', 'ecriture' (contributeur ou administrateur, contrôle fin dans la route),
    'permission', 'composant', 'affectation', 'document' (contrôle sur le paramètre de
    chemin `parametre`) ou 'admin'.
    """

    niveau: str
    permission: str | None = None
    parametre: str | None = None


PUBLIC = Regle("public")
SESSION = Regle("session")
LECTURE = Regle("lecture")
ECRITURE = Regle("ecriture")
ADMIN = Regle("admin")
ACHAT = Regle("permission", ACHATS)
ENSEMBLE = Regle("permission", ENSEMBLES)
COMPOSANT = Regle("composant", parametre="identifiant")

REGLES: dict[tuple[str, str], Regle] = {
    # Session, invitation, santé
    ("GET", "/api/sante"): PUBLIC,
    ("POST", "/api/session"): PUBLIC,
    ("DELETE", "/api/session"): PUBLIC,
    ("GET", "/api/session"): SESSION,
    ("POST", "/api/invitation/verifier"): PUBLIC,
    ("POST", "/api/invitation"): PUBLIC,
    # Utilisateurs
    ("GET", "/api/utilisateurs"): ADMIN,
    ("POST", "/api/utilisateurs"): ADMIN,
    ("PATCH", "/api/utilisateurs/{identifiant}"): ADMIN,
    ("POST", "/api/utilisateurs/{identifiant}/invitation"): ADMIN,
    # Pilotage, paramètres, journal, export
    ("GET", "/api/pilotage"): LECTURE,
    ("GET", "/api/parametres"): LECTURE,
    ("PATCH", "/api/parametres"): ADMIN,
    ("GET", "/api/journal"): LECTURE,
    ("GET", "/api/historique"): LECTURE,
    ("GET", "/api/historique/tables"): LECTURE,
    ("GET", "/api/historique/export"): LECTURE,
    ("POST", "/api/export"): ECRITURE,
    ("GET", "/api/export/classeur"): LECTURE,
    ("GET", "/api/recherche"): LECTURE,
    # Attributs et listes
    ("GET", "/api/attributs"): LECTURE,
    ("POST", "/api/attributs"): ADMIN,
    ("PATCH", "/api/attributs/{code}"): ADMIN,
    ("POST", "/api/attributs/{code}/valeurs"): ADMIN,
    ("PATCH", "/api/attributs/{code}/valeurs/{valeur:path}"): ADMIN,
    ("GET", "/api/attributs/{code}/repartition"): LECTURE,
    ("GET", "/api/attributs/{code}/calcul"): LECTURE,
    ("GET", "/api/listes"): LECTURE,
    ("POST", "/api/listes/{liste}"): ADMIN,
    ("PATCH", "/api/listes/{liste}/{code:path}"): ADMIN,
    ("DELETE", "/api/listes/{liste}/{code:path}"): ADMIN,
    # Blocs
    ("GET", "/api/blocs"): LECTURE,
    ("POST", "/api/blocs"): ADMIN,
    ("GET", "/api/blocs/{code}/prochain-id"): LECTURE,
    ("PATCH", "/api/blocs/{code}"): ADMIN,
    ("GET", "/api/blocs/{code}/modele"): LECTURE,
    # Ensembles et affectations (budgets : contrôle dans la route, réservés à l'administrateur)
    ("GET", "/api/ensembles"): LECTURE,
    ("GET", "/api/ensembles/arbre"): LECTURE,
    ("GET", "/api/ensembles/repartition"): LECTURE,
    ("GET", "/api/ensembles/incoherences"): LECTURE,
    ("GET", "/api/ensembles/{code}"): LECTURE,
    ("POST", "/api/ensembles"): ENSEMBLE,
    ("PATCH", "/api/ensembles/{code}"): ENSEMBLE,
    ("DELETE", "/api/ensembles/{code}"): ENSEMBLE,
    ("GET", "/api/ensembles/{code}/copie"): LECTURE,
    ("POST", "/api/ensembles/{code}/copie"): ENSEMBLE,
    ("GET", "/api/ensembles/{code}/composants"): LECTURE,
    ("GET", "/api/ensembles/{code}/modele"): LECTURE,
    ("POST", "/api/ensembles/{code}/affectations"): ECRITURE,
    ("PATCH", "/api/affectations/{identifiant}"): Regle("affectation", parametre="identifiant"),
    ("DELETE", "/api/affectations/{identifiant}"): Regle("affectation", parametre="identifiant"),
    # Fournisseurs : tout contributeur en propose (« à valider »), la permission achats les
    # modifie, l'administrateur les valide et les archive (contrôle du statut dans la route).
    ("GET", "/api/fournisseurs"): LECTURE,
    ("POST", "/api/fournisseurs"): ECRITURE,
    ("POST", "/api/fournisseurs/comparaison"): ADMIN,
    ("POST", "/api/fournisseurs/comparaison/appliquer"): ADMIN,
    ("GET", "/api/fournisseurs/{nom:path}"): LECTURE,
    ("DELETE", "/api/fournisseurs/{nom:path}"): ADMIN,
    ("PATCH", "/api/fournisseurs/{nom:path}"): ACHAT,
    # Composants
    ("GET", "/api/composants"): LECTURE,
    ("GET", "/api/composants/export"): LECTURE,
    ("GET", "/api/composants/{identifiant}"): LECTURE,
    ("POST", "/api/composants"): ECRITURE,
    ("PATCH", "/api/composants/{identifiant}"): COMPOSANT,
    ("DELETE", "/api/composants/{identifiant}"): COMPOSANT,
    ("POST", "/api/composants/{identifiant}/reclasser"): ADMIN,
    ("PUT", "/api/composants/{identifiant}/attributs"): COMPOSANT,
    # Achats et stock
    ("GET", "/api/commandes"): LECTURE,
    ("GET", "/api/demandes-devis"): LECTURE,
    ("POST", "/api/demandes-devis"): ACHAT,
    ("POST", "/api/commandes"): ACHAT,
    ("GET", "/api/commandes/{numero}"): LECTURE,
    ("PATCH", "/api/commandes/{numero}"): ACHAT,
    ("DELETE", "/api/commandes/{numero}"): ACHAT,
    ("GET", "/api/commandes/{numero}/lignes"): LECTURE,
    ("POST", "/api/commandes/{numero}/lignes"): ACHAT,
    ("PATCH", "/api/commandes/{numero}/lignes/{identifiant}"): ACHAT,
    ("DELETE", "/api/commandes/{numero}/lignes/{identifiant}"): ACHAT,
    ("POST", "/api/commandes/{numero}/reception"): ACHAT,
    ("GET", "/api/stock"): LECTURE,
    ("GET", "/api/mouvements"): LECTURE,
    ("POST", "/api/mouvements"): ECRITURE,
    # Documents
    ("GET", "/api/commandes/{numero}/documents"): LECTURE,
    ("POST", "/api/commandes/{numero}/documents"): ACHAT,
    ("GET", "/api/composants/{identifiant}/documents"): LECTURE,
    ("POST", "/api/composants/{identifiant}/documents"): COMPOSANT,
    ("GET", "/api/documents/{identifiant}/fichier"): LECTURE,
    ("PATCH", "/api/documents/{identifiant}"): Regle("document", parametre="identifiant"),
    ("DELETE", "/api/documents/{identifiant}"): Regle("document", parametre="identifiant"),
    # Imports (application : contrôle ligne par ligne)
    ("GET", "/api/imports"): LECTURE,
    ("POST", "/api/imports"): ECRITURE,
    ("GET", "/api/imports/{depot}"): LECTURE,
    ("POST", "/api/imports/{depot}/appliquer"): ECRITURE,
    ("POST", "/api/imports/{depot}/abandonner"): ECRITURE,
    # Nettoyage
    ("GET", "/api/nettoyage/composants"): LECTURE,
    ("POST", "/api/nettoyage/composants"): ADMIN,
    ("GET", "/api/nettoyage/commandes"): LECTURE,
    ("POST", "/api/nettoyage/commandes"): ADMIN,
    ("GET", "/api/nettoyage/entites"): LECTURE,
    ("DELETE", "/api/nettoyage/entites/{type_entite}/{cle:path}"): ADMIN,
    ("POST", "/api/nettoyage/journal/purge"): ADMIN,
    # Sauvegardes : l'archive contient toute la base
    ("GET", "/api/sauvegardes"): ADMIN,
    ("GET", "/api/sauvegardes/archive"): ADMIN,
    ("GET", "/api/sauvegardes/corbeille"): ADMIN,
    ("POST", "/api/sauvegardes/corbeille/vider"): ADMIN,
    ("POST", "/api/sauvegardes"): ADMIN,
    ("POST", "/api/sauvegardes/{nom}/restaurer"): ADMIN,
}


def get_regle(methode: str, chemin: str) -> Regle:
    """Règle d'une route ; refus par défaut (administrateur) pour une route non déclarée."""
    regle = REGLES.get(("GET" if methode == "HEAD" else methode, chemin))
    if regle is None:
        journal_log.warning(
            "Route sans règle d'accès, réservée à l'administrateur : %s %s", methode, chemin
        )
        return ADMIN
    return regle


def verifier(
    regle: Regle,
    utilisateur: Utilisateur | None,
    conn: sqlite3.Connection,
    parametres: Mapping[str, str],
) -> None:
    """Lève NonConnecte ou AccesRefuse si l'utilisateur ne satisfait pas la règle."""
    if regle.niveau == "public":
        return
    if utilisateur is None:
        raise NonConnecte()
    if regle.niveau == "session":
        return
    if utilisateur.role is None:
        raise AccesRefuse("Votre compte n'a pas accès à ce projet.")
    if regle.niveau == "lecture":
        return
    if regle.niveau == "admin":
        exiger_admin(utilisateur)
        return
    exiger_ecriture(utilisateur)
    match regle.niveau:
        case "ecriture":
            return
        case "permission":
            exiger_permission(utilisateur, str(regle.permission))
        case "composant":
            exiger_composant(conn, utilisateur, parametres[str(regle.parametre)])
        case "affectation":
            exiger_affectation(conn, utilisateur, parametres[str(regle.parametre)])
        case "document":
            exiger_document(conn, utilisateur, parametres[str(regle.parametre)])
        case _:
            raise AccesRefuse("Règle d'accès inconnue.")
