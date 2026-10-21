"""Modèles Pydantic de validation des corps de requête et des réponses de l'API.

Les listes figées reprennent la section « Valeurs autorisées » de docs/MODELE.md ; les listes
paramétrables sont validées contre la table valeur_liste par les services.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, RootModel

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

_SCHEMA_URL = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9+.-]*):")


def _verifier_lien(valeur: str | None) -> str | None:
    """Un lien est une adresse web : un autre schéma (javascript:, data:…) est refusé."""
    if valeur:
        schema = _SCHEMA_URL.match(valeur)
        if schema and schema.group(1).lower() not in ("http", "https"):
            raise ValueError("adresse web attendue (http:// ou https://)")
    return valeur


Lien = Annotated[str | None, AfterValidator(_verifier_lien)]


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
    archive: Literal[0, 1] | None = None


class TraitementLot(Modele):
    """Action en lot de l'écran nettoyage ; `simuler` rend le récapitulatif sans rien faire."""

    cles: list[str] = Field(min_length=1)
    action: Literal["supprimer", "archiver"]
    simuler: bool = False


class PurgeJournal(Modele):
    confirmer: Literal[True]


TypeAttribut = Literal["texte", "nombre", "liste", "booleen"]


class AttributCreation(Modele):
    libelle: str = Field(min_length=1, max_length=60)
    type: TypeAttribut
    unite: str | None = Field(default=None, max_length=20)


class AttributModif(Modele):
    libelle: str | None = Field(default=None, min_length=1, max_length=60)
    unite: str | None = Field(default=None, max_length=20)
    ordre: int | None = None
    actif: Literal[0, 1] | None = None
    obligatoire: Literal[0, 1] | None = None


class AttributValeurCreation(Modele):
    libelle: str = Field(min_length=1, max_length=60)


class AttributValeurModif(Modele):
    libelle: str | None = Field(default=None, min_length=1, max_length=60)
    ordre: int | None = None
    actif: Literal[0, 1] | None = None


class Visas(Modele):
    """Composants à viser par la personne connectée."""

    composants: list[str] = Field(min_length=1)


class ValeursAttributs(Modele):
    """Caractéristiques d'un composant : {code: valeur} ; null efface la valeur."""

    valeurs: dict[str, str | float | bool | None]


class Reclassement(Modele):
    bloc_code: str = Field(pattern=r"^[A-Z]{2,4}$")


class EnsembleCreation(Modele):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]*$", max_length=20)
    nom: str = Field(min_length=1)
    ordre: int = 0
    description: str | None = None
    responsable: str | None = None
    statut_montage: StatutMontage = "Non commence"
    parent_code: str | None = None
    budget_cible_ht: float | None = Field(default=None, ge=0)
    budget_verrouille: bool = False


class EnsembleModif(Modele):
    nom: str | None = Field(default=None, min_length=1)
    ordre: int | None = None
    description: str | None = None
    responsable: str | None = None
    statut_montage: StatutMontage | None = None
    parent_code: str | None = None
    budget_cible_ht: float | None = Field(default=None, ge=0)
    budget_verrouille: bool | None = None


class DemandesDevis(Modele):
    """Composants pour lesquels préparer une demande de devis (une par fournisseur)."""

    composants: list[str] = Field(min_length=1)


class EnsembleDuplication(Modele):
    """Copie d'un ensemble ; parent_code absent = même parent que l'ensemble copié."""

    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]*$", max_length=20)
    nom: str = Field(min_length=1)
    parent_code: str | None = None
    avec_affectations: bool = True
    avec_sous_ensembles: bool = False
    # Nouveau code de chaque sous-ensemble copié ; un code absent reçoit le code proposé.
    codes: dict[str, str] = Field(default_factory=dict)


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
    site_web: Lien = None
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
    site_web: Lien = None
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
    site_web: Lien = None
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
    lien_produit: Lien = None
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
    # Caractéristiques saisies dès la création : {code: valeur}, comme ValeursAttributs.
    attributs: dict[str, str | float | bool | None] = {}


class ComposantModif(Modele):
    fonction: str | None = Field(default=None, min_length=1)
    designation: str | None = Field(default=None, min_length=1)
    mode_appro: ModeAppro | None = None
    qte_besoin: int | None = Field(default=None, ge=0)
    ref_fabricant: str | None = None
    fabricant: str | None = None
    fournisseur_nom: str | None = None
    lien_produit: Lien = None
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
    # Caractéristiques modifiées en même temps que les champs : {code: valeur}, null efface.
    attributs: dict[str, str | float | bool | None] | None = None
    # Date de modification lue avant l'édition : si elle a changé depuis, la modification
    # est refusée plutôt que d'écraser celle d'un autre.
    modifie_le: str | None = None


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
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    reference_externe: str | None = None
    lien_document: Lien = None
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
    taux_tva: float | None = Field(default=None, ge=0, lt=1)
    reference_externe: str | None = None
    lien_document: Lien = None
    commentaire: str | None = None
    # Suivi tenu par l'établissement (services/suivi_achats.py).
    date_transmission_suivi: str | None = Field(default=None, pattern=MOTIF_DATE)
    montant_commande_ht: float | None = Field(default=None, ge=0)
    date_reception_annoncee: str | None = Field(default=None, pattern=MOTIF_DATE)
    commentaire_suivi: str | None = None


class RetenuesSuivi(RootModel[dict[str, list[str]]]):
    """Changements du suivi retenus par l'utilisateur : {numéro de commande: [champs]}."""


class FraisCreation(Modele):
    type_frais: str = Field(min_length=1)
    montant_ht: float = Field(ge=0)
    commentaire: str | None = None


class FraisModif(Modele):
    type_frais: str | None = Field(default=None, min_length=1)
    montant_ht: float | None = Field(default=None, ge=0)
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


# Champs de base qu'un projet peut rendre obligatoires (services/obligatoires.py).
ChampObligatoire = Literal[
    "lien_produit", "fournisseur_nom", "ref_fabricant", "fabricant", "pu_releve"
]


class ParametresModif(Modele):
    nom_projet: str | None = Field(default=None, min_length=1)
    prefixe_id: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,10}$")
    budget_ht: float | None = Field(default=None, ge=0)
    taux_tva_defaut: float | None = Field(default=None, ge=0, lt=1)
    champs_obligatoires: list[ChampObligatoire] | None = None
    champs_obligatoires_portee: Literal["achat", "tous"] | None = None
    # Coordonnées de l'établissement, reprises dans les demandes de devis.
    etablissement_nom: str | None = Field(default=None, max_length=120)
    adresse_livraison: str | None = Field(default=None, max_length=500)
    adresse_facturation: str | None = Field(default=None, max_length=500)
    contact_achats_nom: str | None = Field(default=None, max_length=120)
    contact_achats_mail: str | None = Field(default=None, max_length=120)
    contact_achats_tel: str | None = Field(default=None, max_length=40)


# --- Comptes ------------------------------------------------------------------------------------


class ModeleSecret(BaseModel):
    """Corps portant un mot de passe ou un jeton : rien n'est retouché, pas même les espaces."""

    model_config = ConfigDict(extra="forbid")


class Connexion(ModeleSecret):
    identifiant: str = Field(min_length=1, max_length=254)
    mot_de_passe: str = Field(min_length=1, max_length=1024)


class InvitationVerification(ModeleSecret):
    jeton: str = Field(min_length=1, max_length=128)


class InvitationAcceptation(ModeleSecret):
    jeton: str = Field(min_length=1, max_length=128)
    mot_de_passe: str = Field(min_length=1, max_length=1024)


Role = Literal["lecteur", "contributeur", "administrateur"]
Permission = Literal["achats", "ensembles", "attributs"]


class UtilisateurCreation(Modele):
    identifiant: str = Field(min_length=3, max_length=254)
    nom: str = Field(min_length=1, max_length=60)
    role: Role
    blocs: list[str] = []
    permissions: list[Permission] = []


class UtilisateurModif(Modele):
    nom: str | None = Field(default=None, min_length=1, max_length=60)
    role: Role | None = None
    blocs: list[str] | None = None
    permissions: list[Permission] | None = None
    actif: bool | None = None


# --- Hiérarchie ---------------------------------------------------------------------------------

CODE_ADRESSE = r"^[a-z0-9][a-z0-9-]{0,39}$"
Profil = Literal["gestion", "lecture", "achats_stock"]


class OrganismeCreation(Modele):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,35}$")
    nom: str = Field(min_length=1, max_length=80)


class OrganismeModif(Modele):
    nom: str = Field(min_length=1, max_length=80)


class DossierCreation(Modele):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,29}$")
    nom: str = Field(min_length=1, max_length=80)
    nom_projet: str | None = Field(default=None, max_length=80)


class DossierModif(Modele):
    nom: str | None = Field(default=None, min_length=1, max_length=80)
    nom_projet: str | None = Field(default=None, max_length=80)


class ProjetCreation(Modele):
    code: str = Field(pattern=CODE_ADRESSE)
    nom_equipe: str = Field(min_length=1, max_length=80)
    prefixe_id: str = Field(pattern=r"^[A-Z0-9]{1,10}$")
    admin_identifiant: str | None = Field(default=None, min_length=3, max_length=254)
    admin_nom: str | None = Field(default=None, min_length=1, max_length=60)
    # Projet du même dossier dont on reprend les réglages propres (listes locales, ensembles).
    modele: str | None = Field(default=None, pattern=CODE_ADRESSE)


class ProjetModif(Modele):
    dossier: str | None = Field(default=None, pattern=CODE_ADRESSE)
    nom_equipe: str | None = Field(default=None, max_length=80)
    budget_ht: float | None = Field(default=None, ge=0)


class MembreOrganisme(Modele):
    identifiant: str = Field(min_length=3, max_length=254)
    nom: str = Field(min_length=1, max_length=60)
    profil: Profil


class ProfilModif(Modele):
    profil: Profil


class ResponsableAchats(Modele):
    utilisateur_id: int
