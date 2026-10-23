"""Commandes communes à un dossier (phase 16) : droits, en-tête, lignes, frais, lecture.

Une commune est passée à un fournisseur pour plusieurs projets du dossier. Son en-tête et ses
frais vivent dans la référence du dossier, ses lignes dans la copie de chaque projet présent ;
les parts se déduisent (services/communes_sync.py, qui porte aussi la règle de la version).

Qui fait quoi : les responsables achats du dossier et les profils d'organisme « gestion » et
« achats et stock » créent et modifient (l'« acheteur commun ») ; quiconque voit le dossier
lit. Dans un projet, la copie est en lecture seule (déclencheurs de la migration 025).
"""

import logging
import sqlite3
from datetime import date
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import communes_sync, hierarchie, journal, listes, parametres, reference
from backend.services.communes_sync import Emplacements
from backend.services.droits import ACHATS_STOCK, GESTION, AccesRefuse, Utilisateur
from backend.services.projets import Registre

journal_log = logging.getLogger(__name__)

CHAMPS_EN_TETE: frozenset[str] = frozenset(
    {
        "type",
        "statut",
        "fournisseur_nom",
        "demande_par",
        "date_demande",
        "date_reception_devis",
        "date_commande",
        "livraison_annoncee",
        "taux_tva",
        "reference_externe",
        "lien_document",
        "commentaire",
        "date_transmission_suivi",
        "montant_commande_ht",
        "date_reception_annoncee",
        "commentaire_suivi",
        "archive",
    }
)
CHAMPS_LIGNE: frozenset[str] = frozenset(
    {"qte_commandee", "pu_ht_devis", "statut_ligne", "commentaire"}
)
CHAMPS_FRAIS: frozenset[str] = frozenset({"type_frais", "montant_ht", "commentaire"})
# Livré et Livré partiel se déduisent des réceptions, ils ne se posent pas à la main.
STATUTS_DEDUITS: frozenset[str] = frozenset({"Livre partiel", "Livre"})


# --- Droits et emplacements ---------------------------------------------------------------------


def peut_acheter(conn: sqlite3.Connection, compte: Utilisateur, dossier: dict) -> bool:
    return (
        compte.admin_serveur
        or hierarchie.get_profil(conn, compte, dossier["organisme"]) in (GESTION, ACHATS_STOCK)
        or hierarchie.est_responsable(conn, compte, dossier["code"])
    )


def _dossier(conn: sqlite3.Connection, compte: Utilisateur, code: str, ecriture: bool) -> dict:
    dossier = hierarchie.get_dossier(conn, code)
    hierarchie.exiger_vue_dossier(conn, compte, dossier)
    if ecriture and not peut_acheter(conn, compte, dossier):
        raise AccesRefuse(
            "Les commandes communes se gèrent par les responsables achats du dossier."
        )
    return dossier


def dossier_acheteur(conn: sqlite3.Connection, compte: Utilisateur, code: str) -> dict:
    return _dossier(conn, compte, code, ecriture=True)


def emplacements(conn: sqlite3.Connection, registre: Registre, dossier: dict) -> Emplacements:
    ref = registre.projets.get(reference.code_reference(dossier["code"]))
    if ref is None:
        raise ErreurMetier("La référence du dossier est hors ligne : réessayer plus tard.", 503)
    org = registre.projets.get(reference.code_organisme(dossier["organisme"]))
    codes = reference.projets_du_dossier(conn, dossier["code"])
    return Emplacements(
        dossier=dossier["code"],
        reference=ref.base,
        organisme=org.base if org else None,
        projets={c: registre.projets[c].base for c in codes if c in registre.projets},
        hors_ligne={c for c in codes if c not in registre.projets},
    )


def _noms(conn: sqlite3.Connection, codes: list[str]) -> dict[str, str]:
    """Nom affiché de chaque projet : son équipe, à défaut son code."""
    noms = {}
    for code in codes:
        ligne = conn.execute("SELECT nom_equipe FROM projet WHERE code = ?", (code,)).fetchone()
        noms[code] = (ligne[0] if ligne else None) or code
    return noms


def _ouvrir_ref(emp: Emplacements, compte: Utilisateur) -> sqlite3.Connection:
    return db.connect(emp.reference, compte.nom, creer=False)


def _get(ref: sqlite3.Connection, numero: str, active: bool = True) -> dict:
    commune = communes_sync.lire_commune(ref, numero)
    if commune is None or (active and commune["archive"]):
        raise Introuvable(f"Commande commune « {numero} » introuvable ou archivée.")
    return commune


# --- Liste et lecture ---------------------------------------------------------------------------


def list_communes(
    conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, code: str
) -> dict:
    """Communes non archivées du dossier, les plus récentes d'abord."""
    dossier = _dossier(conn, compte, code, ecriture=False)
    emp = emplacements(conn, registre, dossier)
    ref = db.connect(emp.reference, creer=False)
    try:
        lignes = db.fetch_all(
            ref,
            "SELECT * FROM commune WHERE archive = 0 ORDER BY cree_le DESC, numero DESC",
        )
        participants = {
            c["numero"]: communes_sync.lire_participants(ref, c["numero"]) for c in lignes
        }
    finally:
        ref.close()
    noms = _noms(conn, sorted({p for ps in participants.values() for p in ps}))
    for commune in lignes:
        commune["statut_affiche"] = commune["statut_deduit"] or commune["statut"]
        commune["projets"] = [noms[p] for p in participants[commune["numero"]]]
    return {"acheteur": peut_acheter(conn, compte, dossier), "communes": lignes}


def get_commune(
    conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, code: str, numero: str
) -> dict:
    """Commune avec ses lignes par projet, ses frais et la part de chaque projet.

    Une copie en retard sur la version de la commune (écriture interrompue) est rattrapée.
    """
    dossier = _dossier(conn, compte, code, ecriture=False)
    emp = emplacements(conn, registre, dossier)
    if numero in communes_sync.en_retard(emp):
        communes_sync.synchroniser(emp, numero)
    return _lecture(conn, emp, numero, peut_acheter(conn, compte, dossier))


def _lecture(conn: sqlite3.Connection, emp: Emplacements, numero: str, acheteur: bool) -> dict:
    ref = db.connect(emp.reference, creer=False)
    try:
        commune = _get(ref, numero, active=False)
        participants = communes_sync.lire_participants(ref, numero)
        frais = communes_sync.lire_frais(ref, numero)
        types_frais = db.fetch_all(
            ref,
            "SELECT code, libelle, actif FROM valeur_liste WHERE liste = 'type_frais'"
            " ORDER BY ordre, libelle",
        )
    finally:
        ref.close()
    manquants = sorted(p for p in participants if p not in emp.projets)
    lignes = {
        p: communes_sync.lignes_du_projet(emp.projets[p], n)
        for p, n in participants.items()
        if p in emp.projets
    }
    parts = communes_sync.repartir(lignes, frais, commune["montant_commande_ht"])
    noms = _noms(conn, list(participants))
    projets = [
        {
            "projet": p,
            "nom": noms[p],
            "numero_local": n,
            "lignes": lignes.get(p, []),
            "part": parts.get(p),
            "hors_ligne": p in manquants,
        }
        for p, n in participants.items()
    ]
    return {
        **commune,
        "dossier": emp.dossier,
        "statut_affiche": commune["statut_deduit"] or commune["statut"],
        "acheteur": acheteur,
        "projets": projets,
        "frais": frais,
        "nb_presents": sum(1 for p in parts.values() if p["present"]),
        "estime_ht": sum(p["estime_ht"] for p in parts.values()),
        "manquants": manquants,
        "types_frais": types_frais,
        "nom_dossier": _nom_dossier(conn, emp.dossier),
    }


def _nom_dossier(conn: sqlite3.Connection, code: str) -> dict:
    ligne = conn.execute(
        "SELECT d.nom, o.code AS organisme, o.nom AS nom_organisme FROM dossier d"
        " JOIN organisme o ON o.code = d.organisme WHERE d.code = ?",
        (code,),
    ).fetchone()
    return dict(ligne) if ligne else {}


def list_fournisseurs(emp: Emplacements) -> list[str]:
    """Noms de la liste de l'organisme (fournisseurs validés, non archivés)."""
    if emp.organisme is None:
        return []
    org = db.connect(emp.organisme, creer=False)
    try:
        return [
            ligne[0]
            for ligne in org.execute(
                "SELECT nom FROM fournisseur WHERE archive = 0 AND statut = 'Valide' ORDER BY nom"
            ).fetchall()
        ]
    finally:
        org.close()


def list_candidats(
    conn: sqlite3.Connection, registre: Registre, compte: Utilisateur, code: str, numero: str
) -> list[dict]:
    """Composants achetés et actifs de chaque projet en ligne, avec leur reste à commander.

    L'écran en tire la liste à cocher (fournisseur de la commune, reste > 0) et le choix
    à la main (tout composant actif du projet).
    """
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)
    noms = _noms(conn, list(emp.projets))
    resultat = []
    for projet, base in sorted(emp.projets.items()):
        lecture = db.connect(base, creer=False)
        try:
            composants = db.fetch_all(
                lecture,
                "SELECT id, designation, fournisseur_nom, reste_a_commander, pu_ht"
                " FROM v_composant WHERE mode_appro = 'Achat' ORDER BY id",
            )
        finally:
            lecture.close()
        resultat.append({"projet": projet, "nom": noms[projet], "composants": composants})
    return resultat


# --- En-tête ------------------------------------------------------------------------------------


def _prochain_numero(ref: sqlite3.Connection, emp: Emplacements) -> str:
    numeros = [0, *communes_sync.numeros_des_projets(list(emp.projets.values()))]
    for (numero,) in ref.execute("SELECT numero FROM commune").fetchall():
        correspondance = communes_sync.MOTIF_NUMERO.match(numero)
        if correspondance:
            numeros.append(int(correspondance.group(1)))
    return f"CC-{max(numeros) + 1:03d}"


def _check_fournisseur(emp: Emplacements, nom: str) -> None:
    if emp.organisme is not None and nom not in list_fournisseurs(emp):
        raise ErreurMetier(f"« {nom} » n'est pas un fournisseur validé de la liste de l'organisme.")


def _check_statut(valeurs: dict[str, Any]) -> None:
    if valeurs.get("statut") in STATUTS_DEDUITS:
        raise ErreurMetier(
            "Livré et Livré partiel se déduisent des réceptions : ils ne se posent pas à la main."
        )


def create_commune(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    code: str,
    valeurs: dict[str, Any],
) -> dict:
    """Crée une commune vide ; ses projets la rejoignent avec leur première ligne."""
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)
    _check_fournisseur(emp, valeurs["fournisseur_nom"])
    _check_statut(valeurs)
    ref = _ouvrir_ref(emp, compte)
    try:
        if valeurs.get("taux_tva") is None:
            valeurs["taux_tva"] = parametres.get_taux_tva_defaut(ref)
        with db.transaction(ref):
            numero = _prochain_numero(ref, emp)
            db.insert_row(ref, "commune", {"numero": numero, **valeurs})
            journal.write_journal(ref, "commune", numero, "creation", None, "créée")
    finally:
        ref.close()
    journal_log.info("Commune %s créée dans le dossier %s par %s", numero, code, compte.nom)
    return _lecture(conn, emp, numero, True)


def patch_commune(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    code: str,
    numero: str,
    modifs: dict[str, Any],
) -> dict:
    """Modifie l'en-tête (ou archive : `archive` = 1), puis accorde les copies."""
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)
    _check_statut(modifs)
    if "fournisseur_nom" in modifs:
        _check_fournisseur(emp, modifs["fournisseur_nom"])
    ref = _ouvrir_ref(emp, compte)
    try:
        avant = _get(ref, numero)
        apres = {**avant, **modifs}
        engagee = communes_sync.est_engagee(apres["type"], apres["statut"])
        if engagee and not apres.get("date_commande"):
            modifs = {**modifs, "date_commande": date.today().isoformat()}
        communes_sync.augmenter_version(ref, numero)
        with db.transaction(ref):
            journal.update_with_journal(ref, "commune", numero, modifs, CHAMPS_EN_TETE)
    finally:
        ref.close()
    rapport = communes_sync.synchroniser(emp, numero, compte.nom)
    return {**_lecture(conn, emp, numero, True), "synchronisation": rapport}


# --- Lignes -------------------------------------------------------------------------------------


def _check_projet(emp: Emplacements, projet: str) -> None:
    if projet in emp.hors_ligne:
        raise ErreurMetier(f"Le projet « {projet} » est hors ligne : réessayer plus tard.", 503)
    if projet not in emp.projets:
        raise ErreurMetier(f"Le projet « {projet} » n'est pas dans ce dossier.")


def _numero_local(
    ref: sqlite3.Connection, emp: Emplacements, commune: dict, projet: str, auteur: str
) -> str:
    """Numéro de la copie du projet : créée dans le projet d'abord, inscrite ensuite."""
    participants = communes_sync.lire_participants(ref, commune["numero"])
    if projet in participants:
        return participants[projet]
    numero_local = communes_sync.creer_copie(emp.projets[projet], auteur, commune)
    with db.transaction(ref):
        db.insert_row(
            ref,
            "commune_projet",
            {"numero": commune["numero"], "projet": projet, "numero_local": numero_local},
        )
    return numero_local


def _inserer_lignes(
    base: Any, auteur: str, commune: dict, numero_local: str, lignes: list[dict]
) -> None:
    conn = db.connect(base, auteur, creer=False)
    try:
        engagee = communes_sync.est_engagee(commune["type"], commune["statut"])
        with communes_sync.ouverte(conn):
            communes_sync.assurer_copie(conn, commune, numero_local)
            for ligne in lignes:
                if not db.fetch_one(
                    conn,
                    "SELECT 1 FROM composant WHERE id = ? AND archive = 0",
                    (ligne["composant_id"],),
                ):
                    raise Introuvable(
                        f"Composant « {ligne['composant_id']} » introuvable ou archivé."
                    )
                valeurs = {k: v for k, v in ligne.items() if k != "projet"}
                valeurs["statut_ligne"] = "Commandee" if engagee else "A commander"
                identifiant = db.insert_row(
                    conn, "ligne_commande", {"commande_numero": numero_local, **valeurs}
                )
                journal.write_journal(
                    conn,
                    "commande",
                    numero_local,
                    f"ligne {identifiant}",
                    None,
                    ligne["composant_id"],
                )
    finally:
        conn.close()


def add_lignes(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    code: str,
    numero: str,
    lignes: list[dict],
) -> dict:
    """Ajoute des lignes, chacune dans la copie de son projet (créée au besoin)."""
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)
    par_projet: dict[str, list[dict]] = {}
    for ligne in lignes:
        _check_projet(emp, ligne["projet"])
        par_projet.setdefault(ligne["projet"], []).append(ligne)
    ref = _ouvrir_ref(emp, compte)
    try:
        _get(ref, numero)
        communes_sync.augmenter_version(ref, numero)
        commune = _get(ref, numero)
        locaux = {p: _numero_local(ref, emp, commune, p, compte.nom) for p in par_projet}
    finally:
        ref.close()
    for projet, lignes_projet in par_projet.items():
        _inserer_lignes(emp.projets[projet], compte.nom, commune, locaux[projet], lignes_projet)
    rapport = communes_sync.synchroniser(emp, numero, compte.nom)
    return {**_lecture(conn, emp, numero, True), "synchronisation": rapport}


def _ecrire_ligne(
    emp: Emplacements, compte: Utilisateur, numero: str, projet: str, action: Any
) -> None:
    """Version d'abord, puis l'écriture dans la copie du projet (règle de la version)."""
    _check_projet(emp, projet)
    ref = _ouvrir_ref(emp, compte)
    try:
        _get(ref, numero)
        numero_local = communes_sync.lire_participants(ref, numero).get(projet)
        if numero_local is None:
            raise Introuvable(f"Le projet « {projet} » n'a pas de ligne dans {numero}.")
        communes_sync.augmenter_version(ref, numero)
    finally:
        ref.close()
    base = db.connect(emp.projets[projet], compte.nom, creer=False)
    try:
        with communes_sync.ouverte(base):
            action(base, numero_local)
    finally:
        base.close()


def _get_ligne(conn: sqlite3.Connection, numero_local: str, identifiant: int) -> dict:
    ligne = db.fetch_one(
        conn,
        "SELECT * FROM ligne_commande WHERE id = ? AND commande_numero = ?",
        (identifiant, numero_local),
    )
    if ligne is None:
        raise Introuvable(f"Ligne {identifiant} introuvable.")
    return ligne


def patch_ligne(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    cible: tuple[str, str, str, int],
    modifs: dict[str, Any],
) -> dict:
    """Modifie une ligne (quantité, prix, commentaire, annulation) ; cible : dossier, commune,
    projet, identifiant."""
    code, numero, projet, identifiant = cible
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)

    def modifier(base: sqlite3.Connection, numero_local: str) -> None:
        _get_ligne(base, numero_local, identifiant)
        journal.update_with_journal(base, "ligne_commande", identifiant, modifs, CHAMPS_LIGNE)

    _ecrire_ligne(emp, compte, numero, projet, modifier)
    rapport = communes_sync.synchroniser(emp, numero, compte.nom)
    return {**_lecture(conn, emp, numero, True), "synchronisation": rapport}


def delete_ligne(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    cible: tuple[str, str, str, int],
) -> dict:
    """Supprime une ligne sans réception ; refusé une fois des pièces reçues."""
    code, numero, projet, identifiant = cible
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)

    def supprimer(base: sqlite3.Connection, numero_local: str) -> None:
        ligne = _get_ligne(base, numero_local, identifiant)
        if ligne["qte_recue"] > 0:
            raise Conflit(
                "Des pièces ont déjà été reçues sur cette ligne : elle ne peut pas être "
                "supprimée. Passez-la au statut Annulée si besoin."
            )
        base.execute("DELETE FROM ligne_commande WHERE id = ?", (identifiant,))
        journal.write_journal(
            base, "commande", numero_local, f"ligne {identifiant}", ligne["composant_id"], None
        )

    _ecrire_ligne(emp, compte, numero, projet, supprimer)
    rapport = communes_sync.synchroniser(emp, numero, compte.nom)
    return {**_lecture(conn, emp, numero, True), "synchronisation": rapport}


# --- Frais --------------------------------------------------------------------------------------


def ecrire_frais(
    conn: sqlite3.Connection,
    registre: Registre,
    compte: Utilisateur,
    cible: tuple[str, str, int | None],
    valeurs: dict[str, Any] | None,
) -> dict:
    """Ajoute (identifiant None), modifie ou retire (valeurs None) un frais de la commune."""
    code, numero, identifiant = cible
    dossier = _dossier(conn, compte, code, ecriture=True)
    emp = emplacements(conn, registre, dossier)
    ref = _ouvrir_ref(emp, compte)
    try:
        _get(ref, numero)
        if valeurs and valeurs.get("type_frais") is not None:
            listes.check_valeur(ref, "type_frais", valeurs["type_frais"])
        communes_sync.augmenter_version(ref, numero)
        with db.transaction(ref):
            _frais(ref, numero, identifiant, valeurs)
    finally:
        ref.close()
    rapport = communes_sync.synchroniser(emp, numero, compte.nom)
    return {**_lecture(conn, emp, numero, True), "synchronisation": rapport}


def _frais(
    ref: sqlite3.Connection, numero: str, identifiant: int | None, valeurs: dict[str, Any] | None
) -> None:
    if identifiant is None:
        cree = db.insert_row(ref, "frais_commune", {"numero": numero, **(valeurs or {})})
        journal.write_journal(
            ref,
            "frais_commune",
            f"{numero}:{cree}",
            "montant_ht",
            None,
            (valeurs or {})["montant_ht"],
        )
        return
    frais = db.fetch_one(
        ref, "SELECT * FROM frais_commune WHERE id = ? AND numero = ?", (identifiant, numero)
    )
    if frais is None:
        raise Introuvable(f"Frais n° {identifiant} introuvable.")
    cle = f"{numero}:{identifiant}"
    if valeurs is None:
        ref.execute("DELETE FROM frais_commune WHERE id = ?", (identifiant,))
        journal.write_journal(
            ref,
            "frais_commune",
            cle,
            "montant_ht",
            f"{frais['type_frais']} {frais['montant_ht']}",
            None,
        )
        return
    journal.update_with_journal(
        ref, "frais_commune", identifiant, valeurs, CHAMPS_FRAIS, cle_journal=cle
    )


# --- Rattrapage au démarrage --------------------------------------------------------------------


def reprendre(conn: sqlite3.Connection, registre: Registre) -> None:
    """Communes dont une copie est en retard (écriture interrompue) : resynchronisées."""
    for (code,) in conn.execute("SELECT code FROM dossier WHERE archive = 0").fetchall():
        try:
            emp = emplacements(conn, registre, hierarchie.get_dossier(conn, code))
            for numero in communes_sync.en_retard(emp):
                communes_sync.synchroniser(emp, numero)
        except (sqlite3.Error, OSError, ErreurMetier) as erreur:
            journal_log.error("Dossier %s : communes non reprises au démarrage : %s", code, erreur)
