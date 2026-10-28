"""Suivi des achats tenu par l'établissement : un classeur Excel imposé, en aller-retour.

L'établissement fournit son modèle (en-tête, légende des couleurs, colonnes, ligne TOTAL).
Nomentrace le lit et l'écrit sans en changer la forme :

- aller : chaque devis transmis au suivi y ajoute une ligne par composant (fournisseur,
  référence, désignation, quantité, montant HT, date du devis) et une par frais ;
- retour : les colonnes remplies par l'établissement (dates de commande et de livraison,
  réception, montant de la commande, commentaire) et la couleur de chaque ligne (commandé,
  livré) deviennent des propositions, appliquées seulement si l'utilisateur les retient.

Les copies des commandes communes n'y figurent pas : la commune y a ses propres lignes
(« CC-003 · projet · composant »), lues et écrites depuis la page du dossier
(services/suivi_communes.py). Ici, ces lignes sont ignorées.

Chaque ligne écrite porte sa référence Nomentrace dans une colonne masquée à droite du
modèle (« CMD-012 · ESSAI-ALI-003 », « CMD-012 · frais 4 ») : c'est elle qui retrouve la
ligne au retour. Les colonnes sont reconnues par leur titre, pas par leur position.

Une ligne saisie à la main, sans référence, peut être associée à une commande transmise :
même fournisseur, puis même référence fabricant, désignation très proche ou, pour un frais,
même montant (`associer`). Retenue, l'association écrit la référence dans la colonne
masquée, et la commande n'est pas ajoutée une seconde fois.

L'établissement fusionne volontiers les cases d'une commande (fournisseur, dates, montant
de la commande) sur toutes ses lignes : une cellule fusionnée n'est jamais écrite, et sa
valeur se lit dans la première case du bloc.
"""

import io
import logging
import re
import sqlite3
import unicodedata
from collections import Counter
from copy import copy
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell, MergedCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import commandes
from backend.services import import_doublons as doublons

journal_log = logging.getLogger(__name__)

PREFIXE_COMMUNE = "CC-"

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
        # Cellule secondaire d'un bloc fusionné → première case du bloc, qui porte la valeur.
        self.fusions: dict[tuple[int, int], tuple[int, int]] = {
            (rang, colonne): (bloc.min_row, bloc.min_col)
            for bloc in feuille.merged_cells.ranges
            for rang in range(bloc.min_row, bloc.max_row + 1)
            for colonne in range(bloc.min_col, bloc.max_col + 1)
            if (rang, colonne) != (bloc.min_row, bloc.min_col)
        }
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

    def fusionnee(self, rang: int, cle: str) -> bool:
        """Case secondaire d'un bloc fusionné : sa valeur est celle du bloc, déjà comptée."""
        colonne = self.colonnes.get(cle)
        return colonne is not None and (rang, colonne) in self.fusions

    def valeur_affichee(self, rang: int, cle: str) -> Any:
        """Ce qu'on lit dans la case, fusion comprise (première case du bloc)."""
        colonne = self.colonnes.get(cle)
        if not colonne:
            return None
        rang, colonne = self.fusions.get((rang, colonne), (rang, colonne))
        return self.feuille.cell(rang, colonne).value


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


def ouvrir(contenu: bytes) -> tuple[Any, Modele]:
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


def releve_commandes(modele: Modele, communes: bool = False) -> tuple[dict[str, dict], list[int]]:
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
        if communes and not numero.startswith(PREFIXE_COMMUNE):
            continue
        if not communes and numero.startswith(PREFIXE_COMMUNE):
            # Ligne d'une commande commune : elle se lit depuis la page du dossier.
            continue
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


def propositions_commande(commande: dict, releve: dict) -> dict[str, Any]:
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
        if not identique(commande.get(champ), valeur)
    }


def identique(avant: Any, apres: Any) -> bool:
    if isinstance(avant, (int, float)) and isinstance(apres, (int, float)):
        return abs(avant - apres) < 0.01
    return avant == apres


def decrire_inconnues(modele: Modele, inconnues: list) -> list[str]:
    """« ligne 18 : Stepper Online · Nema 34 » pour une ligne ; un numéro reste tel quel."""
    textes = []
    for inconnue in inconnues:
        if not isinstance(inconnue, int):
            textes.append(inconnue)
            continue
        lu = [modele.valeur_affichee(inconnue, cle) for cle in ("fournisseur", "designation")]
        contenu = " · ".join(str(v).strip() for v in lu if v and str(v).strip())
        textes.append(f"ligne {inconnue} : {contenu}" if contenu else f"ligne {inconnue}")
    return textes


def _absentes(modele: Modele, transmises: list[dict]) -> list[dict]:
    presentes = {modele.reference(rang) for rang in modele.lignes()}
    return [ligne for ligne in transmises if ligne["ref"] not in presentes]


def analyse(conn: sqlite3.Connection, contenu: bytes) -> dict:
    """Propositions tirées du classeur, et nombre de lignes qu'il recevra en plus.

    Les associations proposées sont supposées retenues pour lire le classeur : une commande
    associée reçoit les propositions de ses lignes saisies à la main.
    """
    _, modele = ouvrir(contenu)
    transmises = lignes_a_transmettre(conn)
    associations = associer(modele, _absentes(modele, transmises))
    marquer(modele, associations)
    releves, inconnues = releve_commandes(modele)
    propositions = []
    for numero, releve in sorted(releves.items()):
        commande = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero,))
        if commande is None:
            inconnues.append(numero)
            continue
        changements = propositions_commande(commande, releve)
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
    a_ajouter = _absentes(modele, transmises)
    return {
        "nb_lignes_a_completer": nb_lignes_a_completer(modele, transmises),
        "propositions": propositions,
        "associations": associations,
        "lignes_inconnues": decrire_inconnues(modele, inconnues),
        "nb_lignes_a_ajouter": len(a_ajouter),
        "commandes_a_ajouter": sorted({ligne["numero"] for ligne in a_ajouter}),
    }


def appliquer(
    conn: sqlite3.Connection,
    contenu: bytes,
    retenues: dict[str, list[str]],
    associations: list[str] | None = None,
) -> bytes:
    """Associe les lignes saisies à la main des commandes retenues (`associations`), applique
    les changements retenus ({numéro: [champs]}), puis complète le classeur."""
    classeur, modele = ouvrir(contenu)
    transmises = lignes_a_transmettre(conn)
    voulues = set(associations or [])
    proposees = associer(modele, _absentes(modele, transmises))
    marquer(modele, [a for a in proposees if a["numero"] in voulues])
    releves, _ = releve_commandes(modele)
    for numero, champs in retenues.items():
        commande = db.fetch_one(conn, "SELECT * FROM commande WHERE numero = ?", (numero,))
        if commande is None or numero not in releves:
            continue
        changements = propositions_commande(commande, releves[numero])
        retenu = {c: v for c, v in changements.items() if c in champs}
        if retenu:
            commandes.patch_commande(conn, numero, retenu)
    ajouter_lignes(modele, transmises)
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


# --- Lignes saisies à la main : association à une commande transmise ---------------------------


def _cle_fournisseur(nom: Any) -> str:
    """« Stepper Online », « StepperOnline » et « STEPPER-ONLINE » se valent."""
    return re.sub(r"[^a-z0-9]", "", _norme(nom))


def _lignes_sans_reference(modele: Modele) -> list[dict]:
    """Lignes remplies sans référence Nomentrace. Un fournisseur absent est celui du bloc
    fusionné, sinon celui de la ligne au-dessus (lignes saisies d'un seul tenant)."""
    lignes: list[dict] = []
    fournisseur = None
    for rang in modele.lignes():
        if modele.reference(rang) or _ligne_libre(modele, rang):
            fournisseur = None
            continue
        fournisseur = modele.valeur_affichee(rang, "fournisseur") or fournisseur
        lu = {
            cle: modele.valeur_affichee(rang, cle)
            for cle in ("reference", "designation", "qte", "montant")
        }
        lignes.append({"rang": rang, "fournisseur": fournisseur, **lu})
    return lignes


def _reference_utile(texte: Any) -> str:
    norme = doublons.normaliser(texte)
    return "" if norme in doublons.REMPLISSAGES else norme


def _ressemblance(ligne: dict, saisie: dict) -> float:
    a, b = doublons.normaliser(ligne["designation"]), doublons.normaliser(saisie["designation"])
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _montant_egal(a: Any, b: Any) -> bool:
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 0.01


def _par_designation(lignes: list[dict], saisies: list[dict]) -> list[tuple[dict, dict]]:
    """Meilleures paires d'articles par désignation, au-delà du seuil de fusion de l'import."""
    scores = sorted(
        (
            (_ressemblance(ligne, saisie), i, j)
            for i, ligne in enumerate(lignes)
            if ligne["qte"] is not None
            for j, saisie in enumerate(saisies)
        ),
        reverse=True,
    )
    paires, vus_n, vus_s = [], set(), set()
    for score, i, j in scores:
        if score < doublons.SEUIL_FUSION:
            break
        if i not in vus_n and j not in vus_s:
            vus_n.add(i)
            vus_s.add(j)
            paires.append((lignes[i], saisies[j]))
    return paires


def _apparier(lignes: list[dict], saisies: list[dict]) -> list[tuple[dict, dict]]:
    """Paires (ligne Nomentrace, ligne saisie), chaque ligne prise une fois : même référence
    fabricant, puis désignation très proche, puis, pour un frais, même montant."""
    paires: list[tuple[dict, dict]] = []
    libres_n, libres_s = list(lignes), list(saisies)

    def prendre(ligne: dict, saisie: dict) -> None:
        paires.append((ligne, saisie))
        libres_n.remove(ligne)
        libres_s.remove(saisie)

    for ligne in [x for x in libres_n if x["qte"] is not None]:
        cle = _reference_utile(ligne["reference"])
        saisie = next(
            (s for s in libres_s if cle and _reference_utile(s["reference"]) == cle), None
        )
        if saisie:
            prendre(ligne, saisie)
    for ligne, saisie in _par_designation(libres_n, libres_s):
        prendre(ligne, saisie)
    for ligne in [x for x in libres_n if x["qte"] is None]:
        saisie = next(
            (
                s
                for s in libres_s
                if s["qte"] in (None, "") and _montant_egal(s["montant"], ligne["montant"])
            ),
            None,
        )
        if saisie:
            prendre(ligne, saisie)
    return paires


def _nombre(valeur: float) -> str:
    return str(int(valeur)) if valeur == int(valeur) else f"{valeur:.2f}".replace(".", ",")


def _ecarts(ligne: dict, saisie: dict) -> list[str]:
    ecarts = []
    qte = saisie["qte"]
    if ligne["qte"] is not None and isinstance(qte, (int, float)) and qte != ligne["qte"]:
        ecarts.append(f"quantité {_nombre(qte)} dans le fichier, {ligne['qte']} dans Nomentrace")
    montant = round(ligne["montant"], 2) if ligne["montant"] is not None else None
    lu = saisie["montant"]
    if montant is not None and isinstance(lu, (int, float)) and not _montant_egal(lu, montant):
        ecarts.append(
            f"montant {_nombre(lu)} € dans le fichier, {_nombre(montant)} € dans Nomentrace"
        )
    return ecarts


def associer(modele: Modele, absentes: list[dict]) -> list[dict]:
    """Pour chaque commande transmise absente du classeur, ses lignes saisies à la main.

    `complete` : toutes les lignes de la commande ont trouvé la leur ; l'écran coche alors
    l'association d'office. Les écarts (quantité, montant) sont signalés, jamais corrigés."""
    saisies = _lignes_sans_reference(modele)
    par_commande: dict[str, list[dict]] = {}
    for ligne in absentes:
        par_commande.setdefault(ligne["numero"], []).append(ligne)
    resultats = []
    for numero, lignes in par_commande.items():
        cle = _cle_fournisseur(lignes[0]["fournisseur"])
        candidates = [s for s in saisies if cle and _cle_fournisseur(s["fournisseur"]) == cle]
        paires = sorted(_apparier(lignes, candidates), key=lambda p: p[1]["rang"])
        if not paires:
            continue
        for _, saisie in paires:
            saisies.remove(saisie)
        appariees = [ligne for ligne, _ in paires]
        resultats.append(
            {
                "numero": numero,
                "fournisseur": lignes[0]["fournisseur"],
                "complete": len(paires) == len(lignes),
                "lignes": [
                    {
                        "ligne": saisie["rang"],
                        "ref": ligne["ref"],
                        "designation": saisie["designation"] or ligne["designation"],
                        "ecarts": _ecarts(ligne, saisie),
                    }
                    for ligne, saisie in paires
                ],
                "manquantes": [x["designation"] for x in lignes if x not in appariees],
            }
        )
    return resultats


def marquer(modele: Modele, associations: list[dict]) -> None:
    """Écrit la référence Nomentrace des lignes associées dans la colonne masquée."""
    for association in associations:
        for ligne in association["lignes"]:
            _ecrire(modele.feuille.cell(ligne["ligne"], modele.col_reference), ligne["ref"])


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
        " WHERE c.archive = 0 AND c.commune IS NULL AND c.date_transmission_suivi IS NOT NULL"
        " AND l.statut_ligne <> 'Annulee' ORDER BY c.numero, l.id",
    )
    frais = db.fetch_all(
        conn,
        "SELECT c.numero, c.fournisseur_nom, c.date_reception_devis, f.id, f.montant_ht,"
        " COALESCE(v.libelle, f.type_frais) AS libelle, f.commentaire"
        " FROM commande c JOIN frais_commande f ON f.commande_numero = c.numero"
        " LEFT JOIN valeur_liste v ON v.liste = 'type_frais' AND v.code = f.type_frais"
        " WHERE c.archive = 0 AND c.commune IS NULL AND c.date_transmission_suivi IS NOT NULL"
        " ORDER BY c.numero, f.id",
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
    """Écrit une valeur saisie : jamais une formule, même si le texte commence par « = ».
    Une case secondaire d'un bloc fusionné n'est pas écrite : le bloc a déjà sa valeur."""
    if cellule is None or valeur is None or isinstance(cellule, MergedCell):
        return
    cellule.value = valeur
    if isinstance(valeur, str) and valeur.startswith("="):
        cellule.data_type = "s"


def _ligne_libre(modele: Modele, rang: int) -> bool:
    return not modele.reference(rang) and not any(
        modele.valeur_affichee(rang, cle)
        for cle in ("fournisseur", "reference", "designation", "qte")
    )


def _inserer_avant_total(modele: Modele, nombre: int) -> None:
    """Ajoute des lignes avant le TOTAL, mises en forme comme la première ligne de données,
    et étend les formules de somme du modèle à ces nouvelles lignes."""
    feuille, total = modele.feuille, modele.total
    # openpyxl ne déplace pas les fusions en insérant des lignes : celles du TOTAL et de la
    # légende, dessous, descendent à la main d'autant de lignes.
    dessous = [bloc for bloc in feuille.merged_cells.ranges if bloc.min_row >= total]
    for bloc in dessous:
        feuille.unmerge_cells(bloc.coord)
    feuille.insert_rows(total, nombre)
    for bloc in dessous:
        bloc.shift(row_shift=nombre)
        feuille.merge_cells(bloc.coord)
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


def _valeurs(ligne: dict) -> dict[str, Any]:
    """Ce que Nomentrace écrit d'une ligne, colonne par colonne."""
    return {
        "fournisseur": ligne["fournisseur"],
        "reference": ligne["reference"],
        "designation": ligne["designation"],
        "qte": ligne["qte"],
        "montant": round(ligne["montant"], 2) if ligne["montant"] is not None else None,
        "date_devis": date.fromisoformat(ligne["date_devis"]) if ligne["date_devis"] else None,
    }


def _vide(cellule: Cell | None) -> bool:
    return cellule is not None and (cellule.value is None or str(cellule.value).strip() == "")


def _cases_a_completer(modele: Modele, lignes: list[dict]) -> dict[int, dict[str, Any]]:
    """Lignes déjà écrites par Nomentrace : leurs cases vides qu'il sait maintenant remplir
    (une date de devis saisie après la transmission, par exemple). Une case remplie, par
    l'établissement ou à la main, n'est jamais réécrite."""
    par_ref = {ligne["ref"]: ligne for ligne in lignes}
    cases: dict[int, dict[str, Any]] = {}
    for rang in modele.lignes():
        ligne = par_ref.get(modele.reference(rang) or "")
        if ligne is None:
            continue
        manquantes = {
            cle: valeur
            for cle, valeur in _valeurs(ligne).items()
            if valeur is not None
            and not modele.fusionnee(rang, cle)
            and _vide(modele.cellule(rang, cle))
        }
        if manquantes:
            cases[rang] = manquantes
    return cases


def ajouter_lignes(modele: Modele, lignes: list[dict]) -> None:
    """Complète les cases vides des lignes déjà écrites, puis ajoute les lignes nouvelles."""
    completees = _cases_a_completer(modele, lignes)
    for rang, manquantes in completees.items():
        for cle, valeur in manquantes.items():
            _ecrire(modele.cellule(rang, cle), valeur)
    if completees:
        journal_log.info("Suivi des achats : %d ligne(s) complétée(s)", len(completees))
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
        for cle, valeur in _valeurs(ligne).items():
            _ecrire(modele.cellule(rang, cle), valeur)
        _ecrire(modele.feuille.cell(rang, modele.col_reference), ligne["ref"])
    journal_log.info("Suivi des achats : %d ligne(s) ajoutée(s)", len(nouvelles))


def nb_lignes_a_completer(modele: Modele, lignes: list[dict]) -> int:
    return len(_cases_a_completer(modele, lignes))
