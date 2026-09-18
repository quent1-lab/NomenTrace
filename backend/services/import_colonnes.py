"""Colonnes des fichiers échangés avec l'équipe : modèles générés et fichiers importés."""

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Colonne:
    """Une colonne du modèle : en-tête affiché, champ de la base, nature de la valeur."""

    entete: str
    champ: str
    nature: str  # id, bloc, texte, liste, fournisseur, entier, montant, taux, base
    largeur: int = 16


COLONNES: tuple[Colonne, ...] = (
    Colonne("ID", "id", "id", 15),
    Colonne("Bloc", "bloc_code", "bloc", 8),
    Colonne("Fonction", "fonction", "texte", 28),
    Colonne("Désignation", "designation", "texte", 34),
    Colonne("Réf fabricant", "ref_fabricant", "texte", 20),
    Colonne("Fabricant", "fabricant", "texte", 16),
    Colonne("Mode appro", "mode_appro", "liste", 16),
    Colonne("Fournisseur", "fournisseur_nom", "fournisseur", 18),
    Colonne("Lien produit", "lien_produit", "texte", 30),
    Colonne("Qté besoin", "qte_besoin", "entier", 10),
    Colonne("Qté rechange", "qte_rechange", "entier", 10),
    Colonne("Qté déjà disponible", "qte_disponible", "entier", 12),
    Colonne("PU relevé", "pu_releve", "montant", 11),
    Colonne("Base prix", "base_prix_releve", "base", 9),
    Colonne("Taux TVA", "taux_tva", "taux", 9),
    Colonne("Statut choix", "statut_choix", "liste", 14),
    Colonne("Statut appro", "statut_appro", "liste", 14),
    Colonne("Criticité", "criticite", "liste", 12),
    Colonne("Origine exigence", "origine_exigence", "texte", 16),
    Colonne("Note technique", "note_technique", "texte", 40),
)
COLONNE_QTE_ENSEMBLE = Colonne("Qté dans cet ensemble", "qte_ensemble", "entier", 12)
COLONNE_ENSEMBLE = Colonne("Ensemble", "ensemble_code", "ensemble", 16)

# Champs du composant comparés et modifiables par import (le bloc est figé dans l'ID).
CHAMPS_COMPOSANT: tuple[str, ...] = tuple(
    c.champ for c in COLONNES if c.champ not in ("id", "bloc_code")
)
OBLIGATOIRES: dict[str, str] = {
    "fonction": "Fonction",
    "designation": "Désignation",
    "mode_appro": "Mode appro",
    "qte_besoin": "Qté besoin",
}

NOM_FEUILLE = "Composants"
NOM_FEUILLE_META = "_nomentrace"
NOM_FEUILLE_LISTES = "_listes"


def normaliser_entete(texte: str) -> str:
    """En-tête comparable : minuscules, sans accents, lettres et chiffres seulement."""
    decompose = unicodedata.normalize("NFKD", str(texte).lower())
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sans_accents)


# En-têtes reconnus : ceux des modèles, et des variantes courantes (fichier Airtable d'origine
# et saisies libres de l'équipe).
ALIAS_ENTETES: dict[str, str] = {
    **{
        normaliser_entete(c.entete): c.champ
        for c in (*COLONNES, COLONNE_QTE_ENSEMBLE, COLONNE_ENSEMBLE)
    },
    "codeensemble": "ensemble_code",
    "identifiant": "id",
    "blocfonctionnel": "bloc_code",
    "reference": "ref_fabricant",
    "reffabricant": "ref_fabricant",
    "modedapprovisionnement": "mode_appro",
    "fournisseurprivilegie": "fournisseur_nom",
    "lien": "lien_produit",
    "qtedispoecole": "qte_disponible",
    "qtedisponible": "qte_disponible",
    "pureleve": "pu_releve",
    "prixunitaire": "pu_releve",
    "baseprixreleve": "base_prix_releve",
    "tva": "taux_tva",
    "qteensemble": "qte_ensemble",
    "quantitedanscetensemble": "qte_ensemble",
}
