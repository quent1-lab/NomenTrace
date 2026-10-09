"""Suivi des achats tenu par l'établissement : un classeur Excel imposé, en aller-retour.

L'établissement fournit son modèle (en-tête, légende des couleurs, colonnes, ligne TOTAL).
Nomentrace le lit et l'écrit sans en changer la forme :

- aller : chaque devis transmis au suivi y ajoute une ligne par composant (fournisseur,
  référence, désignation, quantité, montant HT, date du devis) et une par frais ;
- retour : les colonnes remplies par l'établissement (dates de commande et de livraison,
  réception, montant de la commande, commentaire) et la couleur de chaque ligne (commandé,
  livré) deviennent des propositions, appliquées seulement si l'utilisateur les retient.

Chaque ligne écrite porte sa référence Nomentrace dans une colonne masquée à droite du
modèle (« CMD-012 · ESSAI-ALI-003 », « CMD-012 · frais 4 ») : c'est elle qui retrouve la
ligne au retour. Les colonnes sont reconnues par leur titre, pas par leur position.
"""

import io
import logging
import re
import sqlite3
import unicodedata
from collections import Counter
from copy import copy
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import commandes

journal_log = logging.getLogger(__name__)

TITRE_REFERENCE = "Réf. Nomentrace"
# Titres de colonnes du modèle, reconnus sans accents ni casse, par leur début.
COLONNES: dict[str, tuple[str, ...]] = {
    "fournisseur": ("fournisseur",),
    "reference": ("ref materiel", "reference"),
    "designation": ("designation",),
    "qte": ("qte", "quantite"),
    "montant": ("montant ht",),
    "date_devis": ("date devis",),
    "date_commande": ("date commande",),
    "date_livraison": ("date livraison",),
    "date_reception": ("date reception",),
    "montant_commande": ("montant commande",),
    "commentaire": ("commentaire",),
}
OBLIGATOIRES: tuple[str, ...] = ("fournisseur", "designation", "qte", "montant", "date_devis")


def _norme(texte: Any) -> str:
    """Minuscules, sans accents ni symboles : « montant\\n€  HT » devient « montant ht »."""
    brut = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", brut.replace("\n", " ")).strip().lower()


# --- Lecture du modèle -------------------------------------------------------------------------


class Modele:
    """Positions repérées dans le classeur : en-tête, colonnes, lignes de données, total."""

    def __init__(self, feuille: Worksheet) -> None:
        self.feuille = feuille
        self.ligne_entete, self.colonnes = self._entete()
        self.premiere = self.ligne_entete + 1
        self.total = self._ligne_total()
        self.col_reference = self._colonne_reference()
        self.legende = self._legende()

    def _entete(self) -> tuple[int, dict[str, int]]:
        for ligne in self.feuille.iter_rows(min_row=1, max_row=min(self.feuille.max_row, 40)):
            titres = {cellule.column: _norme(cellule.value) for cellule in ligne if cellule.value}
            colonnes = {}
            for cle, debuts in COLONNES.items():
                for colonne, titre in titres.items():
                    if (
                        any(titre.startswith(_norme(d)) for d in debuts)
                        and colonne not in colonnes.values()
                    ):
                        colonnes.setdefault(cle, colonne)
            if all(cle in colonnes for cle in OBLIGATOIRES):
                return ligne[0].row, colonnes
        raise ErreurMetier(
            "Ce classeur ne ressemble pas au modèle de suivi : aucune ligne de titres avec"
            " « Fournisseur », « Désignation », « Qté », « montant HT » et « date devis »."
        )

    def _ligne_total(self) -> int:
        """Première ligne sous l'en-tête qui contient « TOTAL » ; à défaut, après la dernière."""
        for ligne in self.feuille.iter_rows(min_row=self.premiere, max_row=self.feuille.max_row):
            if any(_norme(c.value) == "total" for c in ligne):
                return ligne[0].row
        return self.feuille.max_row + 1

    def _colonne_reference(self) -> int:
        """Colonne masquée des références : retrouvée par son titre, sinon créée à droite."""
        for cellule in self.feuille[self.ligne_entete]:
            if cellule.value == TITRE_REFERENCE:
                return cellule.column
        colonne = max(self.colonnes.values()) + 1
        self.feuille.cell(self.ligne_entete, colonne, TITRE_REFERENCE)
        self.feuille.column_dimensions[get_column_letter(colonne)].hidden = True
        return colonne

    def _legende(self) -> dict[tuple, str]:
        """Couleur de chaque état, lue dans la légende du modèle (devis, commandé, livré)."""
        legende = {}
        for ligne in self.feuille.iter_rows(min_row=1, max_row=self.ligne_entete - 1):
            for cellule in ligne:
                etat = {
                    "devis": "devis",
                    "commande": "commande",
                    "commandee": "commande",
                    "livre": "livre",
                    "livree": "livre",
                }.get(_norme(cellule.value))
                if etat:
                    legende[cle_couleur(cellule)] = etat
        return legende

    def lignes(self) -> range:
        return range(self.premiere, self.total)

    def reference(self, rang: int) -> str | None:
        valeur = self.feuille.cell(rang, self.col_reference).value
        return str(valeur).strip() if valeur else None

    def valeur(self, rang: int, cle: str) -> Any:
        colonne = self.colonnes.get(cle)
        return self.feuille.cell(rang, colonne).value if colonne else None

    def cellule(self, rang: int, cle: str) -> Cell | None:
        colonne = self.colonnes.get(cle)
        return self.feuille.cell(rang, colonne) if colonne else None


def cle_couleur(cellule: Cell) -> tuple:
    """Empreinte comparable d'un remplissage : sans fond, couleur RVB, ou thème et nuance."""
    remplissage = cellule.fill
    if remplissage is None or remplissage.fill_type in (None, "none"):
        return ("aucun",)
    couleur = remplissage.fgColor
    if couleur.type == "rgb":
        return ("rgb", str(couleur.rgb)[-6:].upper())
    if couleur.type == "theme":
        return ("theme", couleur.theme, round(couleur.tint or 0, 2))
    return (couleur.type, couleur.value)


def _ouvrir(contenu: bytes) -> tuple[Any, Modele]:
    try:
        classeur = load_workbook(io.BytesIO(contenu))
    except (OSError, ValueError, KeyError) as erreur:
        raise ErreurMetier(f"Classeur illisible : {erreur}.") from erreur
    return classeur, Modele(classeur.active)


# --- Retour : ce que l'établissement a rempli ---------------------------------------------------


def _iso(valeur: Any) -> str | None:
    if isinstance(valeur, datetime):
        return valeur.date().isoformat()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        trouve = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", valeur)
        if trouve:
            jour, mois, annee = (int(x) for x in trouve.groups())
            return date(annee, mois, jour).isoformat()
    return None


def _bleu(cellule: Cell | None) -> bool:
    """Police bleue : date confirmée (noire : estimée), selon la note du modèle."""
    couleur = cellule.font.color if cellule is not None and cellule.font else None
    if couleur is None:
        return False
    if couleur.type == "theme":
        return couleur.theme in (4, 8, 10)
    if couleur.type == "rgb" and isinstance(couleur.rgb, str):
        r, v, b = (int(couleur.rgb[-6:][i : i + 2], 16) for i in (0, 2, 4))
        return b > 120 and b > r + 40 and b > v
    return False


def _etat_ligne(modele: Modele, rang: int) -> str:
    """État d'une ligne d'après sa couleur, comparée à la légende ; sans couleur : devis."""
    couleurs = Counter(
        cle_couleur(modele.feuille.cell(rang, colonne)) for colonne in modele.colonnes.values()
    )
    couleurs.pop(("aucun",), None)
    for couleur, _ in couleurs.most_common():
        if couleur in modele.legende:
            return modele.legende[couleur]
    return "devis"


def _releve_commandes(modele: Modele) -> tuple[dict[str, dict], list[int]]:
    """Ce que dit le classeur de chaque commande, et les lignes sans référence Nomentrace."""
    releves: dict[str, dict] = {}
    inconnues = []
    for rang in modele.lignes():
        reference = modele.reference(rang)
        if not reference:
            if any(modele.valeur(rang, cle) for cle in ("fournisseur", "designation")):
                inconnues.append(rang)
            continue
        numero = reference.split("·")[0].strip()
        r = releves.setdefault(numero, {"etats": [], "montants": [], "commentaires": []})
        r["etats"].append(_etat_ligne(modele, rang))
        for cle, champ, confirme in (
            ("date_commande", "date_commande", "date_commande_confirmee"),
            ("date_livraison", "livraison_annoncee", "livraison_confirmee"),
        ):
            iso = _iso(modele.valeur(rang, cle))
            if iso and champ not in r:
                r[champ] = iso
                r[confirme] = int(_bleu(modele.cellule(rang, cle)))
        reception = _iso(modele.valeur(rang, "date_reception"))
        if reception:
            r["date_reception_annoncee"] = max(reception, r.get("date_reception_annoncee", ""))
        montant = modele.valeur(rang, "montant_commande")
        if isinstance(montant, (int, float)):
            r["montants"].append(float(montant))
        commentaire = modele.valeur(rang, "commentaire")
        if commentaire and str(commentaire).strip() not in r["commentaires"]:
            r["commentaires"].append(str(commentaire).strip())
    return releves, inconnues


def _propositions_commande(commande: dict, releve: dict) -> dict[str, Any]:
    """Champs de la commande que le classeur ferait changer."""
    cibles: dict[str, Any] = {}
    etats = set(releve["etats"])
    # Commandé ou livré : la commande est passée. « Livré » ne réceptionne rien : la
    # réception, avec ses quantités, reste à saisir dans Nomentrace.
    if etats & {"commande", "livre"} and not commandes.STATUTS_ENGAGES & {commande["statut"]}:
        cibles["type"] = "Commande"
        cibles["statut"] = "Commande"
    for champ in (
        "date_commande",
        "date_commande_confirmee",
        "livraison_annoncee",
        "livraison_confirmee",
        "date_reception_annoncee",
    ):
        if champ in releve:
            cibles[champ] = releve[champ]
    # Livré sans date de réception : la couleur suffit, datée du jour où on l'apprend.
    if (
        etats == {"livre"}
        and "date_reception_annoncee" not in releve
        and not commande.get("date_reception_annoncee")
    ):
        cibles["date_reception_annoncee"] = date.today().isoformat()
    if releve["montants"]:
        # Une valeur pour la commande ; saisie sur plusieurs lignes, elle s'additionne.
        cibles["montant_commande_ht"] = round(sum(releve["montants"]), 2)
    if releve["commentaires"]:
        cibles["commentaire_suivi"] = " ; ".join(releve["commentaires"])
    return {
        champ: valeur
        for champ, valeur in cibles.items()
        if not _identique(commande.get(champ), valeur)
    }


def _identique(avant: Any, apres: Any) -> bool:
    if isinstance(avant, (int, float)) and isinstance(apres, (int, float)):
        return abs(avant - apres) < 0.01
    return avant == apres


def analyse(conn: sqlite3.Connection, contenu: bytes) -> dict:
    """Propositions tirées du classeur, et nombre de lignes qu'il recevra en plus."""
    _, modele = _ouvrir(contenu)
    releves, inconnues = _releve_commandes(modele)
    propositions = []
    for numero, releve in sorted(releves.items()):
        commande = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero,))
        if commande is None:
            inconnues.append(numero)
            continue
        changements = _propositions_commande(commande, releve)
        if changements:
            propositions.append(
                {
                    "numero": numero,
                    "fournisseur": commande["fournisseur_nom"],
                    "changements": [
                        {"champ": c, "avant": commande.get(c), "apres": v}
                        for c, v in changements.items()
                    ],
                }
            )
    presentes = {modele.reference(rang) for rang in modele.lignes()}
    a_ajouter = [ligne for ligne in lignes_a_transmettre(conn) if ligne["ref"] not in presentes]
    return {
        "propositions": propositions,
        "lignes_inconnues": [f"ligne {i}" if isinstance(i, int) else i for i in inconnues],
        "nb_lignes_a_ajouter": len(a_ajouter),
        "commandes_a_ajouter": sorted({ligne["numero"] for ligne in a_ajouter}),
    }


def appliquer(conn: sqlite3.Connection, contenu: bytes, retenues: dict[str, list[str]]) -> bytes:
    """Applique les changements retenus ({numéro: [champs]}), puis complète le classeur."""
    classeur, modele = _ouvrir(contenu)
    releves, _ = _releve_commandes(modele)
    for numero, champs in retenues.items():
        commande = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero,))
        if commande is None or numero not in releves:
            continue
        changements = _propositions_commande(commande, releves[numero])
        retenu = {c: v for c, v in changements.items() if c in champs}
        if retenu:
            commandes.patch_commande(conn, numero, retenu)
    _ajouter_lignes(modele, lignes_a_transmettre(conn))
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


# --- Aller : les devis transmis au suivi --------------------------------------------------------


def lignes_a_transmettre(conn: sqlite3.Connection) -> list[dict]:
    """Une ligne par composant et par frais des commandes transmises au suivi."""
    articles = db.fetch_all(
        conn,
        "SELECT c.numero, c.fournisseur_nom, c.date_reception_devis, l.composant_id,"
        " p.ref_fabricant, p.designation, l.qte_commandee,"
        " l.qte_commandee * l.pu_ht_devis AS montant"
        " FROM commande c JOIN ligne_commande l ON l.commande_numero = c.numero"
        " JOIN composant p ON p.id = l.composant_id"
        " WHERE c.archive = 0 AND c.date_transmission_suivi IS NOT NULL"
        " AND l.statut_ligne <> 'Annulee' ORDER BY c.numero, l.id",
    )
    frais = db.fetch_all(
        conn,
        "SELECT c.numero, c.fournisseur_nom, c.date_reception_devis, f.id, f.montant_ht,"
        " COALESCE(v.libelle, f.type_frais) AS libelle, f.commentaire"
        " FROM commande c JOIN frais_commande f ON f.commande_numero = c.numero"
        " LEFT JOIN valeur_liste v ON v.liste = 'type_frais' AND v.code = f.type_frais"
        " WHERE c.archive = 0 AND c.date_transmission_suivi IS NOT NULL ORDER BY c.numero, f.id",
    )
    lignes = [
        {
            "ref": f"{a['numero']} · {a['composant_id']}",
            "numero": a["numero"],
            "fournisseur": a["fournisseur_nom"],
            "reference": a["ref_fabricant"],
            "designation": a["designation"],
            "qte": a["qte_commandee"],
            "montant": a["montant"],
            "date_devis": a["date_reception_devis"],
        }
        for a in articles
    ]
    lignes += [
        {
            "ref": f"{f['numero']} · frais {f['id']}",
            "numero": f["numero"],
            "fournisseur": f["fournisseur_nom"],
            "reference": None,
            "designation": f"{f['libelle']} ({f['commentaire']})"
            if f["commentaire"]
            else f["libelle"],
            "qte": None,
            "montant": f["montant_ht"],
            "date_devis": f["date_reception_devis"],
        }
        for f in frais
    ]
    return sorted(lignes, key=lambda ligne: ligne["numero"])


def _ecrire(cellule: Cell | None, valeur: Any) -> None:
    """Écrit une valeur saisie : jamais une formule, même si le texte commence par « = »."""
    if cellule is None or valeur is None:
        return
    cellule.value = valeur
    if isinstance(valeur, str) and valeur.startswith("="):
        cellule.data_type = "s"


def _ligne_libre(modele: Modele, rang: int) -> bool:
    return not modele.reference(rang) and not any(
        modele.valeur(rang, cle) for cle in ("fournisseur", "reference", "designation", "qte")
    )


def _inserer_avant_total(modele: Modele, nombre: int) -> None:
    """Ajoute des lignes avant le TOTAL, mises en forme comme la première ligne de données,
    et étend les formules de somme du modèle à ces nouvelles lignes."""
    feuille, total = modele.feuille, modele.total
    feuille.insert_rows(total, nombre)
    modele_ligne = modele.premiere
    for rang in range(total, total + nombre):
        for colonne in range(1, modele.col_reference + 1):
            source = feuille.cell(modele_ligne, colonne)
            cible = feuille.cell(rang, colonne)
            if source.has_style:
                cible._style = copy(source._style)
                # Ni la couleur d'état ni la police bleue d'une date confirmée ne se recopient :
                # une ligne neuve est un devis, sans date.
                cible.fill = PatternFill(fill_type=None)
                cible.font = Font(
                    name=source.font.name, size=source.font.size, bold=source.font.bold
                )
    nouveau_total = total + nombre
    for cellule in feuille[nouveau_total]:
        if isinstance(cellule.value, str) and cellule.value.startswith("="):
            cellule.value = re.sub(
                r"([A-Z]+)(\d+):([A-Z]+)(\d+)",
                lambda m: (
                    f"{m[1]}{m[2]}:{m[3]}{nouveau_total - 1}" if int(m[4]) == total - 1 else m[0]
                ),
                cellule.value,
            )
    modele.total = nouveau_total


def _ajouter_lignes(modele: Modele, lignes: list[dict]) -> None:
    presentes = {modele.reference(rang) for rang in modele.lignes()}
    nouvelles = [ligne for ligne in lignes if ligne["ref"] not in presentes]
    if not nouvelles:
        return
    libres = [rang for rang in modele.lignes() if _ligne_libre(modele, rang)]
    # Les lignes libres d'abord, après la dernière ligne remplie ; puis des lignes ajoutées.
    derniere = max((r for r in modele.lignes() if not _ligne_libre(modele, r)), default=0)
    libres = [rang for rang in libres if rang > derniere]
    if len(libres) < len(nouvelles):
        manque = len(nouvelles) - len(libres)
        debut = modele.total
        _inserer_avant_total(modele, manque)
        libres += list(range(debut, debut + manque))
    for rang, ligne in zip(libres, nouvelles, strict=False):
        _ecrire(modele.cellule(rang, "fournisseur"), ligne["fournisseur"])
        _ecrire(modele.cellule(rang, "reference"), ligne["reference"])
        _ecrire(modele.cellule(rang, "designation"), ligne["designation"])
        _ecrire(modele.cellule(rang, "qte"), ligne["qte"])
        _ecrire(
            modele.cellule(rang, "montant"),
            round(ligne["montant"], 2) if ligne["montant"] is not None else None,
        )
        if ligne["date_devis"]:
            _ecrire(modele.cellule(rang, "date_devis"), date.fromisoformat(ligne["date_devis"]))
        modele.feuille.cell(rang, modele.col_reference, ligne["ref"])
    journal_log.info("Suivi des achats : %d ligne(s) ajoutée(s)", len(nouvelles))
