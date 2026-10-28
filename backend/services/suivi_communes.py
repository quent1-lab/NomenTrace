"""Suivi de l'établissement pour les commandes communes d'un dossier (phase 16b).

Même classeur, même aller-retour que le suivi d'un projet (services/suivi_achats.py), mais
pour les communes transmises du dossier. Une commune y figure par ses lignes de composants,
une par ligne de chaque projet, et par ses frais : « CC-003 · eqa · EQA-ALI-003 »,
« CC-003 · frais 4 ». Les copies dans les projets n'y figurent pas.

Montant réel lu au retour (décision du 2026-10-23) :
- toutes les lignes non annulées de la commune ont un montant dans le classeur : il est lu
  ligne par ligne, la part d'un projet est la somme de ses lignes plus sa part des frais
  saisis sur la commune (mode « lignes ») ;
- sinon, la somme des montants lus est un total, réparti au prorata de l'estimé (« total »).
"""

import io
import logging
import sqlite3
from typing import Any

from backend import db
from backend.services import communes, communes_sync, journal, suivi_achats
from backend.services.communes_sync import Emplacements
from backend.services.droits import Utilisateur
from backend.services.projets import Registre

journal_log = logging.getLogger(__name__)


def _ref_ligne(numero: str, projet: str, composant: str) -> str:
    return f"{numero} · {projet} · {composant}"


def _articles(base: Any, numero_local: str) -> list[dict]:
    conn = db.connect(base, creer=False)
    try:
        return db.fetch_all(
            conn,
            "SELECT l.composant_id, p.ref_fabricant, p.designation, l.qte_commandee,"
            " l.qte_commandee * l.pu_ht_devis AS montant"
            " FROM ligne_commande l JOIN composant p ON p.id = l.composant_id"
            " WHERE l.commande_numero = ? AND l.statut_ligne <> 'Annulee' ORDER BY l.id",
            (numero_local,),
        )
    finally:
        conn.close()


def _lignes_commune(emp: Emplacements, ref: sqlite3.Connection, commune: dict) -> list[dict]:
    """Lignes d'une commune pour le classeur : articles de chaque projet en ligne, frais."""
    numero = commune["numero"]
    lignes = []
    for projet, numero_local in communes_sync.lire_participants(ref, numero).items():
        if projet not in emp.projets:
            continue
        for a in _articles(emp.projets[projet], numero_local):
            lignes.append(
                {
                    "ref": _ref_ligne(numero, projet, a["composant_id"]),
                    "projet": projet,
                    "numero": numero,
                    "fournisseur": commune["fournisseur_nom"],
                    "reference": a["ref_fabricant"],
                    "designation": a["designation"],
                    "qte": a["qte_commandee"],
                    "montant": a["montant"],
                    "date_devis": commune["date_reception_devis"],
                }
            )
    for f in communes_sync.lire_frais(ref, numero):
        libelle = f["type_libelle"] or f["type_frais"]
        lignes.append(
            {
                "ref": f"{numero} · frais {f['id']}",
                "projet": None,
                "numero": numero,
                "fournisseur": commune["fournisseur_nom"],
                "reference": None,
                "designation": f"{libelle} ({f['commentaire']})" if f["commentaire"] else libelle,
                "qte": None,
                "montant": f["montant_ht"],
                "date_devis": commune["date_reception_devis"],
            }
        )
    return lignes


def lignes_a_transmettre(emp: Emplacements) -> list[dict]:
    """Une ligne par article et par frais des communes transmises au suivi."""
    ref = db.connect(emp.reference, creer=False)
    try:
        transmises = db.fetch_all(
            ref,
            "SELECT * FROM commune WHERE archive = 0 AND date_transmission_suivi IS NOT NULL"
            " ORDER BY numero",
        )
        return [ligne for c in transmises for ligne in _lignes_commune(emp, ref, c)]
    finally:
        ref.close()


def _montants_lus(modele: suivi_achats.Modele) -> dict[str, float]:
    montants = {}
    for rang in modele.lignes():
        reference = modele.reference(rang)
        montant = modele.valeur(rang, "montant_commande")
        if reference and isinstance(montant, (int, float)):
            montants[reference] = float(montant)
    return montants


def _reel_par_ligne(
    emp: Emplacements, ref: sqlite3.Connection, commune: dict, montants: dict[str, float]
) -> dict[str, float] | None:
    """Somme lue par projet, si toutes les lignes non annulées ont un montant ; sinon None."""
    articles = [
        ligne for ligne in _lignes_commune(emp, ref, commune) if ligne["projet"] is not None
    ]
    if not articles or any(ligne["ref"] not in montants for ligne in articles):
        return None
    par_projet: dict[str, float] = {}
    for ligne in articles:
        par_projet[ligne["projet"]] = par_projet.get(ligne["projet"], 0.0) + montants[ligne["ref"]]
    return par_projet


def _propositions(
    emp: Emplacements,
    ref: sqlite3.Connection,
    commune: dict,
    releve: dict,
    montants: dict[str, float],
) -> tuple[dict[str, Any], dict[str, float] | None]:
    """Champs de la commune que le classeur ferait changer, et les montants par projet."""
    cibles = suivi_achats.propositions_commande(commune, releve)
    par_ligne = _reel_par_ligne(emp, ref, commune, montants)
    mode = None
    if par_ligne is not None:
        mode = "lignes"
        frais = sum(f["montant_ht"] for f in communes_sync.lire_frais(ref, commune["numero"]))
        reel = sum(par_ligne.values()) + frais
        cibles.pop("montant_commande_ht", None)
        if not suivi_achats.identique(commune["montant_commande_ht"], reel):
            cibles["montant_commande_ht"] = reel
    elif releve["montants"]:
        mode = "total"
    # Le mode est proposé quand il change, ou quand les montants par projet changent.
    deja = communes_sync.lire_reel_lignes(ref, commune)
    if mode is not None and (
        commune["mode_reel"] != mode or (mode == "lignes" and deja != par_ligne)
    ):
        cibles["mode_reel"] = mode
    return cibles, par_ligne


def analyse(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    code: str,
    contenu: bytes,
) -> dict:
    """Propositions tirées du classeur pour les communes du dossier, et lignes à ajouter."""
    emp = communes.emplacements(conn, registre, communes.dossier_acheteur(conn, compte, code))
    _, modele = suivi_achats.ouvrir(contenu)
    releves, inconnues = suivi_achats.releve_commandes(modele, communes=True)
    montants = _montants_lus(modele)
    propositions = []
    ref = db.connect(emp.reference, creer=False)
    try:
        for numero, releve in sorted(releves.items()):
            commune = communes_sync.lire_commune(ref, numero)
            if commune is None:
                inconnues.append(numero)
                continue
            changements, _ = _propositions(emp, ref, commune, releve, montants)
            if changements:
                propositions.append(
                    {
                        "numero": numero,
                        "fournisseur": commune["fournisseur_nom"],
                        "changements": [
                            {"champ": c, "avant": commune.get(c), "apres": v}
                            for c, v in changements.items()
                        ],
                    }
                )
    finally:
        ref.close()
    presentes = {modele.reference(rang) for rang in modele.lignes()}
    transmises = lignes_a_transmettre(emp)
    a_ajouter = [ligne for ligne in transmises if ligne["ref"] not in presentes]
    return {
        "nb_lignes_a_completer": suivi_achats.nb_lignes_a_completer(modele, transmises),
        "propositions": propositions,
        "lignes_inconnues": suivi_achats.decrire_inconnues(modele, inconnues),
        "nb_lignes_a_ajouter": len(a_ajouter),
        "commandes_a_ajouter": sorted({ligne["numero"] for ligne in a_ajouter}),
    }


def _ecrire(
    emp: Emplacements,
    compte: Utilisateur,
    numero: str,
    modifs: dict[str, Any],
    par_ligne: dict[str, float] | None,
) -> None:
    """Version d'abord, puis l'en-tête et les montants par projet, puis synchronisation."""
    ref = db.connect(emp.reference, compte.nom, creer=False)
    try:
        communes_sync.augmenter_version(ref, numero)
        with db.transaction(ref):
            journal.update_with_journal(ref, "commune", numero, modifs, communes.CHAMPS_EN_TETE)
            if modifs.get("mode_reel") is not None:
                lus = par_ligne if modifs["mode_reel"] == "lignes" else {}
                for projet in communes_sync.lire_participants(ref, numero):
                    ref.execute(
                        "UPDATE commune_projet SET reel_lignes_ht = ? WHERE numero = ?"
                        " AND projet = ?",
                        ((lus or {}).get(projet), numero, projet),
                    )
    finally:
        ref.close()
    communes_sync.synchroniser(emp, numero, compte.nom)


def appliquer(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    code: str,
    fichier: tuple[bytes, dict[str, list[str]]],
) -> bytes:
    """Applique les changements retenus ({numéro: [champs]}), puis complète le classeur."""
    contenu, retenues = fichier
    emp = communes.emplacements(conn, registre, communes.dossier_acheteur(conn, compte, code))
    classeur, modele = suivi_achats.ouvrir(contenu)
    releves, _ = suivi_achats.releve_commandes(modele, communes=True)
    montants = _montants_lus(modele)
    for numero, champs in retenues.items():
        ref = db.connect(emp.reference, creer=False)
        try:
            commune = communes_sync.lire_commune(ref, numero)
            if commune is None or commune["archive"] or numero not in releves:
                continue
            changements, par_ligne = _propositions(emp, ref, commune, releves[numero], montants)
        finally:
            ref.close()
        retenu = {c: v for c, v in changements.items() if c in champs}
        # Montant et mode vont ensemble : retenir l'un, c'est retenir l'autre.
        if retenu.keys() & {"montant_commande_ht", "mode_reel"}:
            for champ in ("montant_commande_ht", "mode_reel"):
                if champ in changements:
                    retenu[champ] = changements[champ]
        if retenu:
            _ecrire(emp, compte, numero, retenu, par_ligne)
    suivi_achats.ajouter_lignes(modele, lignes_a_transmettre(emp))
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()
