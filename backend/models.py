"""Modèles Pydantic de validation des corps de requête et des réponses de l'API.

Les listes figées reprennent la section « Valeurs autorisées » de docs/MODELE.md ; les listes
paramétrables sont validées contre la table valeur_liste par les services.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Listes paramétrables (table valeur_liste) : validées contre la base par le service.
ValeurListe = str
ModeAppro = ValeurListe
StatutChoix = ValeurListe
StatutAppro = ValeurListe
Criticite = ValeurListe
BasePrix = Literal["HT", "TTC"]
StatutFournisseur = Literal["Valide", "A valider"]
TypeCommande = Literal["Devis", "Commande"]
StatutCommande = Literal[
    "A demander",
    "Devis demande",
    "Devis recu",
    "Devis valide",
    "Commande",
    "Livre partiel",
    "Livre",
    "Refuse",
]
StatutLigne = Literal["A commander", "Commandee", "Recue partiel", "Recue", "Annulee"]
Sens = Literal["Entree", "Sortie"]
TypeMouvement = ValeurListe
StatutMontage = Literal["Non commence", "En cours", "Monte", "Valide"]

MOTIF_DATE = r"^\d{4}-\d{2}-\d{2}$"


class Modele(BaseModel):
    """Base commune : champs inconnus refusés, espaces de bord retirés."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SanteReponse(BaseModel):
    """État de l'application renvoyé par GET /api/sante."""

    statut: str
    version_schema: int
    nom_projet: str | None
    export_en_attente: bool = False


class BlocCreation(Modele):
    code: str = Field(pattern=r"^[A-Z]{2,4}$")
    nom: str = Field(min_length=1)
    ordre: int | None = None
    budget_cible_ht: float | None = Field(default=None, ge=0)
    responsable: str | None = None
    description: str | None = None


class BlocModif(Modele):
    nom: str | None = Field(default=None, min_length=1)
    ordre: int | None = None
    budget_cible_ht: float | None = Field(default=None, ge=0)
    responsable: str | None = None
    description: str | None = None


class EnsembleCreation(Modele):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]*$", max_length=20)
    nom: str = Field(min_length=1)
    ordre: int = 0
    description: str | None = None
    responsable: str | None = None
    statut_montage: StatutMontage = "Non commence"


class EnsembleModif(Modele):
    nom: str | None = Field(default=None, min_length=1)
    ordre: int | None = None
    description: str | None = None
    responsable: str | None = None
    statut_montage: StatutMontage | None = None


class AffectationCreation(Modele):
    composant_id: str = Field(min_length=1)
    qte: int = Field(gt=0)
    commentaire: str | None = None


class AffectationModif(Modele):
    qte: int | None = Field(default=None, gt=0)
    commentaire: str | None = None


class FournisseurCreation(Modele):
    nom: str = Field(min_length=1)
    type: str | None = None
    base_prix_defaut: BasePrix | None = None
    pays: str | None = None
    site_web: str | None = None
    numero_compte: str | None = None
    categorie: str | None = None
    contact: str | None = None
    delai_moyen_j: int | None = Field(default=None, ge=0)
    commentaire: str | None = None
    statut: StatutFournisseur = "Valide"


class FournisseurModif(Modele):
    nom: str | None = Field(default=None, min_length=1)
    type: str | None = None
    base_prix_defaut: BasePrix | None = None
    pays: str | None = None
    site_web: str | None = None
    numero_compte: str | None = None
    categorie: str | None = None
    contact: str | None = None
    delai_moyen_j: int | None = Field(default=None, ge=0)
    commentaire: str | None = None
    statut: StatutFournisseur | None = None


class ChampsFournisseur(Modele):
    """Champs complétés sur un fournisseur existant depuis une liste (le nom ne change pas)."""

    type: str | None = None
    pays: str | None = None
    site_web: str | None = None
    numero_compte: str | None = None
    categorie: str | None = None
    contact: str | None = None
    delai_moyen_j: int | None = Field(default=None, ge=0)
    commentaire: str | None = None
    statut: StatutFournisseur | None = None


class CompletionFournisseur(Modele):
    nom: str = Field(min_length=1)
    champs: ChampsFournisseur


class ApplicationListeFournisseurs(Modele):
    creations: list[FournisseurCreation] = []
    completions: list[CompletionFournisseur] = []


class ComposantCreation(Modele):
    bloc_code: str = Field(min_length=1)
    fonction: str = Field(min_length=1)
    designation: str = Field(min_length=1)
    mode_appro: ModeAppro
    qte_besoin: int = Field(ge=0)
    ref_fabricant: str | None = None
    fabricant: str | None = None
    fournisseur_nom: str | None = None
    lien_produit: str | None = None
    qte_rechange: int = Field(default=0, ge=0)
    qte_disponible: int = Field(default=0, ge=0)
    pu_releve: float | None = Field(default=None, ge=0)
    base_prix_releve: BasePrix = "HT"
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    statut_choix: StatutChoix | None = None
    statut_appro: StatutAppro = "Non lance"
    criticite: Criticite | None = None
    origine_exigence: str | None = None
    note_technique: str | None = None


class ComposantModif(Modele):
    fonction: str | None = Field(default=None, min_length=1)
    designation: str | None = Field(default=None, min_length=1)
    mode_appro: ModeAppro | None = None
    qte_besoin: int | None = Field(default=None, ge=0)
    ref_fabricant: str | None = None
    fabricant: str | None = None
    fournisseur_nom: str | None = None
    lien_produit: str | None = None
    qte_rechange: int | None = Field(default=None, ge=0)
    qte_disponible: int | None = Field(default=None, ge=0)
    pu_releve: float | None = Field(default=None, ge=0)
    base_prix_releve: BasePrix | None = None
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    statut_choix: StatutChoix | None = None
    statut_appro: StatutAppro | None = None
    criticite: Criticite | None = None
    origine_exigence: str | None = None
    note_technique: str | None = None


class CommandeCreation(Modele):
    type: TypeCommande = "Commande"
    statut: StatutCommande = "A demander"
    fournisseur_nom: str | None = None
    demande_par: str | None = None
    date_demande: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_reception_devis: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_commande: str | None = Field(default=None, pattern=MOTIF_DATE)
    livraison_annoncee: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_reception_reelle: str | None = Field(default=None, pattern=MOTIF_DATE)
    port_ht: float = Field(default=0, ge=0)
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    reference_externe: str | None = None
    lien_document: str | None = None
    commentaire: str | None = None


class CommandeModif(Modele):
    type: TypeCommande | None = None
    statut: StatutCommande | None = None
    fournisseur_nom: str | None = None
    demande_par: str | None = None
    date_demande: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_reception_devis: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_commande: str | None = Field(default=None, pattern=MOTIF_DATE)
    livraison_annoncee: str | None = Field(default=None, pattern=MOTIF_DATE)
    date_reception_reelle: str | None = Field(default=None, pattern=MOTIF_DATE)
    port_ht: float | None = Field(default=None, ge=0)
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    reference_externe: str | None = None
    lien_document: str | None = None
    commentaire: str | None = None


class LigneCreation(Modele):
    composant_id: str = Field(min_length=1)
    qte_commandee: int = Field(gt=0)
    pu_ht_devis: float | None = Field(default=None, ge=0)
    statut_ligne: StatutLigne = "A commander"
    commentaire: str | None = None


class LigneModif(Modele):
    qte_commandee: int | None = Field(default=None, ge=0)
    pu_ht_devis: float | None = Field(default=None, ge=0)
    qte_recue: int | None = Field(default=None, ge=0)
    date_reception: str | None = Field(default=None, pattern=MOTIF_DATE)
    statut_ligne: StatutLigne | None = None
    commentaire: str | None = None


class MouvementCreation(Modele):
    date: str = Field(pattern=MOTIF_DATE)
    composant_id: str = Field(min_length=1)
    sens: Sens | None = None
    type_mouvement: TypeMouvement
    qte: int = Field(gt=0)
    emplacement: str | None = None
    par_qui: str | None = None
    commande_numero: str | None = None
    ensemble_code: str | None = None
    commentaire: str | None = None


class ValeurListeCreation(Modele):
    libelle: str = Field(min_length=1, max_length=60)
    sens: Sens | None = None


class ValeurListeModif(Modele):
    libelle: str | None = Field(default=None, min_length=1, max_length=60)
    ordre: int | None = None
    actif: int | None = Field(default=None, ge=0, le=1)
    sens: Sens | None = None


TypeDocument = Literal[
    "Devis",
    "Bon de commande",
    "Facture",
    "Bon de livraison",
    "Fiche technique",
    "Plan",
    "Photo",
    "Autre",
]


class DocumentModif(Modele):
    type_document: TypeDocument | None = None
    commentaire: str | None = None


class ApplicationImport(Modele):
    """Décisions par ligne d'import : champs retenus, action choisie, cible d'une fusion."""

    decisions: dict[str, dict[str, Any]]


class ReceptionLigne(Modele):
    id: int
    qte: int = Field(ge=0)


class Reception(Modele):
    date: str | None = Field(default=None, pattern=MOTIF_DATE)
    emplacement: str | None = None
    par_qui: str | None = None
    lignes: list[ReceptionLigne] = Field(min_length=1)


class ParametresModif(Modele):
    nom_projet: str | None = Field(default=None, min_length=1)
    prefixe_id: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,10}$")
    budget_ht: float | None = Field(default=None, ge=0)
    taux_tva_defaut: float | None = Field(default=None, ge=0, lt=1)
