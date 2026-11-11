"""Outils offerts à un assistant IA par le protocole MCP : chacun est une route de l'API.

Un outil appelle sa route dans le processus, avec l'identité du compte : mêmes validations,
mêmes droits (table REGLES), même journal, même export que l'interface. Cette liste est
aussi la liste blanche des routes qu'une requête MCP peut atteindre (`ROUTES`) : aucune
suppression, rien de réservé à l'administrateur (budgets, comptes, sauvegardes,
paramètres). Les champs exclus (budgets d'un ensemble) sont retirés du schéma et refusés.

Le schéma d'entrée de chaque outil est tiré de la description OpenAPI de sa route : il suit
les modèles Pydantic sans être recopié.
"""

import re
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI


@dataclass(frozen=True)
class Outil:
    nom: str
    description: str
    methode: str
    chemin: str
    exclus: tuple[str, ...] = ()

    @property
    def lecture(self) -> bool:
        return self.methode == "GET"


BUDGETS = ("budget_cible_ht", "budget_verrouille")

OUTILS: tuple[Outil, ...] = (
    # --- Lecture ---
    Outil(
        "get_pilotage",
        "Tableau de bord du projet : budget, engagé, coûts, avancement des"
        " achats, commandes en retard, bloquants.",
        "GET",
        "/api/pilotage",
    ),
    Outil(
        "search",
        "Recherche plein texte dans les composants, ensembles, commandes et fournisseurs.",
        "GET",
        "/api/recherche",
    ),
    Outil(
        "get_parametres",
        "Paramètres du projet : nom, préfixe des identifiants, budget, TVA"
        " par défaut, établissement.",
        "GET",
        "/api/parametres",
    ),
    Outil(
        "list_listes",
        "Listes de valeurs du projet (mode d'appro, statuts, criticité, types"
        " de mouvement, types de frais) : codes à employer en écriture et leurs libellés.",
        "GET",
        "/api/listes",
    ),
    Outil(
        "list_blocs",
        "Blocs du projet (découpage de suivi, un par composant, figé dans l'identifiant).",
        "GET",
        "/api/blocs",
    ),
    Outil(
        "list_attributs",
        "Attributs des composants et leurs valeurs possibles.",
        "GET",
        "/api/attributs",
    ),
    Outil(
        "list_composants",
        "Composants du projet, filtrables (bloc, ensemble, statuts,"
        " fournisseur…), avec quantités, prix HT et avancement.",
        "GET",
        "/api/composants",
    ),
    Outil(
        "get_composant",
        "Fiche complète d'un composant par son identifiant : affectations,"
        " commandes, stock, attributs, historique.",
        "GET",
        "/api/composants/{identifiant}",
    ),
    Outil(
        "get_ensembles_arbre",
        "Arborescence des ensembles (découpage physique) avec budgets et coûts cumulés.",
        "GET",
        "/api/ensembles/arbre",
    ),
    Outil("list_ensembles", "Ensembles du projet, à plat.", "GET", "/api/ensembles"),
    Outil("get_ensemble", "Détail d'un ensemble par son code.", "GET", "/api/ensembles/{code}"),
    Outil(
        "list_composants_ensemble",
        "Composants affectés à un ensemble, avec la quantité.",
        "GET",
        "/api/ensembles/{code}/composants",
    ),
    Outil("list_fournisseurs", "Fournisseurs du projet.", "GET", "/api/fournisseurs"),
    Outil(
        "get_fournisseur",
        "Détail d'un fournisseur par son nom.",
        "GET",
        "/api/fournisseurs/{nom:path}",
    ),
    Outil(
        "list_commandes",
        "Commandes et devis du projet, avec statut et montants.",
        "GET",
        "/api/commandes",
    ),
    Outil(
        "get_commande", "Détail d'une commande par son numéro.", "GET", "/api/commandes/{numero}"
    ),
    Outil(
        "list_lignes_commande",
        "Lignes d'une commande (lots commandés et reçus, prix d'un lot).",
        "GET",
        "/api/commandes/{numero}/lignes",
    ),
    Outil(
        "list_frais_commande",
        "Frais d'une commande (port, etc.).",
        "GET",
        "/api/commandes/{numero}/frais",
    ),
    Outil("list_stock", "Stock par composant.", "GET", "/api/stock"),
    Outil("list_mouvements", "Mouvements de stock.", "GET", "/api/mouvements"),
    Outil(
        "get_journal",
        "Journal des modifications (qui a changé quoi, quand), le plus récent d'abord. Volumineux :"
        " filtrer par `cle_cible` (identifiant d'un composant, code d'un ensemble, numéro de"
        " commande) ou `table_cible`, et borner par `limite` (500 par défaut).",
        "GET",
        "/api/journal",
    ),
    # --- Écriture ---
    Outil(
        "create_composant",
        "Crée un composant dans un bloc ; son identifiant est généré.",
        "POST",
        "/api/composants",
    ),
    Outil(
        "update_composant",
        "Modifie les champs fournis d'un composant. Passer `modifie_le`"
        " lu juste avant pour refuser d'écraser une modification concurrente.",
        "PATCH",
        "/api/composants/{identifiant}",
    ),
    Outil(
        "set_attributs_composant",
        "Remplace les valeurs d'attributs d'un composant.",
        "PUT",
        "/api/composants/{identifiant}/attributs",
    ),
    Outil(
        "create_ensemble",
        "Crée un ensemble (budgets exclus : ils se règlent dans l'interface).",
        "POST",
        "/api/ensembles",
        BUDGETS,
    ),
    Outil(
        "update_ensemble",
        "Modifie un ensemble (budgets exclus).",
        "PATCH",
        "/api/ensembles/{code}",
        BUDGETS,
    ),
    Outil(
        "create_affectation",
        "Affecte un composant à un ensemble avec une quantité.",
        "POST",
        "/api/ensembles/{code}/affectations",
    ),
    Outil(
        "update_affectation",
        "Modifie la quantité d'une affectation.",
        "PATCH",
        "/api/affectations/{identifiant}",
    ),
    Outil("create_fournisseur", "Propose un fournisseur.", "POST", "/api/fournisseurs"),
    Outil("update_fournisseur", "Modifie un fournisseur.", "PATCH", "/api/fournisseurs/{nom:path}"),
    Outil("create_commande", "Crée une commande ou un devis.", "POST", "/api/commandes"),
    Outil(
        "update_commande",
        "Modifie une commande (statut, dates, montants…).",
        "PATCH",
        "/api/commandes/{numero}",
    ),
    Outil(
        "create_ligne_commande",
        "Ajoute un composant à une commande (quantité en lots).",
        "POST",
        "/api/commandes/{numero}/lignes",
    ),
    Outil(
        "update_ligne_commande",
        "Modifie une ligne de commande.",
        "PATCH",
        "/api/commandes/{numero}/lignes/{identifiant}",
    ),
    Outil(
        "create_frais", "Ajoute des frais à une commande.", "POST", "/api/commandes/{numero}/frais"
    ),
    Outil("update_frais", "Modifie des frais de commande.", "PATCH", "/api/frais/{identifiant}"),
    Outil(
        "create_reception",
        "Enregistre une réception (lots reçus par ligne) ; met le stock à jour.",
        "POST",
        "/api/commandes/{numero}/reception",
    ),
    Outil(
        "create_mouvement",
        "Enregistre un mouvement de stock (entrée, sortie, inventaire).",
        "POST",
        "/api/mouvements",
    ),
    Outil(
        "create_demande_devis",
        "Crée une demande de devis auprès d'un fournisseur.",
        "POST",
        "/api/demandes-devis",
    ),
)

PAR_NOM: dict[str, Outil] = {outil.nom: outil for outil in OUTILS}
# Liste blanche des routes atteignables par une requête MCP, la route MCP comprise.
ROUTES: frozenset[tuple[str, str]] = frozenset(
    {(outil.methode, outil.chemin) for outil in OUTILS} | {("POST", "/api/mcp")}
)

_CONVERTISSEUR = re.compile(r"\{(\w+):\w+\}")
_REFERENCE = "#/components/schemas/"


def chemin_openapi(chemin: str) -> str:
    """`/api/fournisseurs/{nom:path}` → `/api/fournisseurs/{nom}`, clé de la description."""
    return _CONVERTISSEUR.sub(r"{\1}", chemin)


def _references(valeur: Any) -> Any:
    """Réécrit les références OpenAPI en références JSON Schema locales (`$defs`)."""
    if isinstance(valeur, dict):
        return {
            cle: (v.replace(_REFERENCE, "#/$defs/") if cle == "$ref" else _references(v))
            for cle, v in valeur.items()
        }
    if isinstance(valeur, list):
        return [_references(v) for v in valeur]
    return valeur


@dataclass(frozen=True)
class Schema:
    """Schéma d'entrée d'un outil et répartition de ses arguments."""

    entree: dict
    # (argument, paramètre du chemin) : un paramètre homonyme d'un champ du corps (le nom
    # d'un fournisseur qu'on renomme) devient l'argument « <nom>_actuel ».
    chemin: tuple[tuple[str, str], ...]
    requete: tuple[str, ...]
    corps: tuple[str, ...]


def _schema(outil: Outil, description: dict, composants: dict) -> Schema:
    operation = description["paths"][chemin_openapi(outil.chemin)][outil.methode.lower()]
    proprietes: dict[str, Any] = {}
    requis: list[str] = []
    chemin: list[str] = []
    requete: list[str] = []
    for parametre in operation.get("parameters", []):
        nom = parametre["name"]
        proprietes[nom] = parametre.get("schema", {})
        if parametre["in"] == "path":
            chemin.append(nom)
        else:
            requete.append(nom)
        if parametre.get("required"):
            requis.append(nom)
    corps: list[str] = []
    alias: dict[str, str] = {}
    contenu = operation.get("requestBody", {}).get("content", {}).get("application/json")
    if contenu:
        modele = contenu["schema"]
        if "$ref" in modele:
            modele = composants[modele["$ref"].removeprefix(_REFERENCE)]
        for nom, schema in modele.get("properties", {}).items():
            if nom in outil.exclus:
                continue
            if nom in chemin:
                actuel = f"{nom}_actuel"
                proprietes[actuel] = {**proprietes.pop(nom), "description": f"{nom} actuel"}
                requis = [actuel if r == nom else r for r in requis]
                alias[nom] = actuel
            elif nom in proprietes:
                raise ValueError(f"Outil {outil.nom} : champ {nom} en double.")
            proprietes[nom] = schema
            corps.append(nom)
        requis += [nom for nom in modele.get("required", []) if nom not in outil.exclus]
    entree: dict[str, Any] = {
        "type": "object",
        "properties": proprietes,
        "required": requis,
        "additionalProperties": False,
    }
    citees = _citees(proprietes)
    if citees:
        entree["$defs"] = _fermeture(citees, composants)
    arguments_chemin = tuple((alias.get(nom, nom), nom) for nom in chemin)
    return Schema(_references(entree), arguments_chemin, tuple(requete), tuple(corps))


def _citees(valeur: Any) -> set[str]:
    """Noms des définitions OpenAPI citées par une valeur de schéma."""
    if isinstance(valeur, dict):
        noms = {valeur["$ref"].removeprefix(_REFERENCE)} if "$ref" in valeur else set()
        return noms.union(*(_citees(v) for v in valeur.values()))
    if isinstance(valeur, list):
        return set().union(*(_citees(v) for v in valeur))
    return set()


def _fermeture(noms: set[str], composants: dict) -> dict:
    """Définitions citées, et celles qu'elles citent à leur tour."""
    a_voir, vues = list(noms), {}
    while a_voir:
        nom = a_voir.pop()
        if nom not in vues:
            vues[nom] = composants[nom]
            a_voir += _citees(composants[nom])
    return vues


def schemas(app: FastAPI) -> dict[str, Schema]:
    """Schémas de tous les outils, calculés une fois par application."""
    deja = getattr(app.state, "mcp_schemas", None)
    if deja is not None:
        return deja
    description = app.openapi()
    composants = description.get("components", {}).get("schemas", {})
    resultat = {outil.nom: _schema(outil, description, composants) for outil in OUTILS}
    app.state.mcp_schemas = resultat
    return resultat
