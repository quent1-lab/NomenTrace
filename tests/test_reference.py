"""Réglages imposés par un dossier : référence, propagation, verrou (phase 15b-2).

Le projet du jeu d'essai, rangé le premier dans le dossier « spoc », en donne la référence ;
un projet « beta » créé ensuite la reçoit. L'oracle est l'empreinte du contenu imposé
(services/propagation.py), comparée table par table et champ par champ.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from backend.services import authentification, import_application, propagation, reference
from tests.test_comptes import PROJET, connecter, creer_compte, navigateur
from tests.test_hierarchie import (
    _comptes,
    creer_dossier,
    creer_organisme,
    creer_projet,
    membre_organisme,
    ranger,
    serveur,
)

REF = "ref-spoc"
ORG = "org-meca"


@pytest.fixture(autouse=True)
def scrypt_rapide(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authentification, "SCRYPT_N", 2**10)


@pytest.fixture
def code_projet() -> str:
    return PROJET


@pytest.fixture
def app(
    conn_essai: sqlite3.Connection, dossier_data: Path, dossier_echange: Path
) -> Iterator[FastAPI]:
    conn_essai.close()
    application = create_app(
        dossier_data,
        dossier_echange=dossier_echange,
        mode_local=False,
        chemin_comptes=dossier_data / "comptes.db",
        code_projet=PROJET,
    )
    with navigateur(application):
        creer_organisme(application, "meca", "Mécatronique")
        creer_dossier(application, "meca", {"code": "spoc", "nom": "SPOC 2027"})
        yield application


def base(app: FastAPI, code: str) -> Path:
    return app.state.registre.projets[code].base


def empreinte(app: FastAPI, code: str) -> str:
    """Empreinte des tables imposées de `code`, avec la liste de fournisseurs de l'organisme."""
    return propagation.empreinte_base(base(app, code), nom_dossier(app), base(app, ORG))


def nom_dossier(app: FastAPI) -> str | None:
    conn = _comptes(app)
    try:
        return conn.execute("SELECT nom_projet FROM dossier WHERE code = 'spoc'").fetchone()[0]
    finally:
        conn.close()


def contenu(chemin: Path) -> list[str]:
    """Toute la base, sauf la ligne du verrou : sert à prouver qu'aucune ligne n'a changé."""
    conn = sqlite3.connect(chemin)
    try:
        return [ligne for ligne in conn.iterdump() if "reglages_imposes" not in ligne]
    finally:
        conn.close()


def lire(app: FastAPI, code: str, requete: str, params: tuple = ()) -> list[tuple]:
    conn = db.connect(base(app, code), creer=False)
    try:
        return [tuple(r) for r in conn.execute(requete, params).fetchall()]
    finally:
        conn.close()


def nb_journal(app: FastAPI, code: str) -> int:
    return lire(app, code, "SELECT COUNT(*) FROM journal")[0][0]


@pytest.fixture
def range_(app: FastAPI) -> TestClient:
    """Le projet d'essai rangé dans le dossier (il donne la référence), et un serveur connecté."""
    ranger(app, PROJET, {"dossier": "spoc", "nom_equipe": "Alpha"})
    return serveur(app)


# --- 1. Le premier projet rangé donne la référence, sans changer -------------------------------


def test_rangement_initial_donne_la_reference(app: FastAPI) -> None:
    avant = contenu(base(app, PROJET))
    ranger(app, PROJET, {"dossier": "spoc", "nom_equipe": "Alpha"})
    assert contenu(base(app, PROJET)) == avant
    assert nom_dossier(app) == "Projet d'essai"
    assert empreinte(app, REF) == empreinte(app, PROJET)
    blocs_ref = lire(
        app, REF, "SELECT code, nom, ordre, description, archive FROM bloc ORDER BY code"
    )
    blocs = lire(
        app, PROJET, "SELECT code, nom, ordre, description, archive FROM bloc ORDER BY code"
    )
    assert blocs_ref == blocs and len(blocs) >= 5


# --- 2. Un projet créé reçoit la référence -------------------------------------------------------


def test_projet_cree_recoit_la_reference(app: FastAPI, range_: TestClient) -> None:
    creer_projet(range_)
    assert empreinte(app, "beta") == empreinte(app, REF)
    etat = lire(app, "beta", "SELECT actif, empreinte FROM reglages_imposes")[0]
    assert etat == (1, empreinte(app, REF))


# --- 3. Une modification de la référence est propagée -------------------------------------------


def test_modification_de_la_reference_propagee(app: FastAPI, range_: TestClient) -> None:
    creer_projet(range_)
    locaux_avant = lire(
        app, PROJET, "SELECT code, budget_cible_ht, responsable FROM bloc ORDER BY code"
    )
    ecritures = [
        ("PATCH", f"/p/{REF}/api/blocs/ALI", {"nom": "Alimentation générale"}),
        ("POST", f"/p/{REF}/api/listes/criticite", {"libelle": "Urgent"}),
        ("POST", f"/p/{REF}/api/attributs", {"libelle": "Tension", "type": "nombre", "unite": "V"}),
        (
            "PATCH",
            f"/p/{REF}/api/parametres",
            {"taux_tva_defaut": 0.055, "etablissement_nom": "École"},
        ),
    ]
    for methode, adresse, corps in ecritures:
        reponse = range_.request(methode, adresse, json=corps)
        assert reponse.status_code < 300, reponse.text
    voulue = empreinte(app, REF)
    for code in (PROJET, "beta"):
        assert empreinte(app, code) == voulue, code
        assert lire(app, code, "SELECT nom FROM bloc WHERE code = 'ALI'") == [
            ("Alimentation générale",)
        ]
    assert (
        lire(app, PROJET, "SELECT code, budget_cible_ht, responsable FROM bloc ORDER BY code")
        == locaux_avant
    )


def test_resynchronisation_sans_effet(app: FastAPI, range_: TestClient) -> None:
    """Rejouer une synchronisation à jour n'écrit rien, pas même une ligne de journal."""
    avant = nb_journal(app, PROJET)
    conn = _comptes(app)
    try:
        reference.propager(conn, app.state.registre, "spoc")
    finally:
        conn.close()
    assert nb_journal(app, PROJET) == avant


# --- 4. Une valeur utilisée n'est jamais supprimée ----------------------------------------------


def test_valeur_utilisee_desactivee_inutilisee_supprimee(app: FastAPI, range_: TestClient) -> None:
    # « Fabrication atelier » sert à un composant du jeu d'essai, « Stock interne » à aucun.
    utilises = lire(
        app, PROJET, "SELECT COUNT(*) FROM composant WHERE mode_appro = 'Fabrication atelier'"
    )[0][0]
    assert utilises > 0
    for code in ("Fabrication atelier", "Stock interne"):
        reponse = range_.delete(f"/p/{REF}/api/listes/mode_appro/{code}")
        assert reponse.status_code == 200, reponse.text
    valeurs = dict(
        lire(app, PROJET, "SELECT code, actif FROM valeur_liste WHERE liste = 'mode_appro'")
    )
    assert valeurs.get("Fabrication atelier") == 0
    assert "Stock interne" not in valeurs
    apres = lire(
        app, PROJET, "SELECT COUNT(*) FROM composant WHERE mode_appro = 'Fabrication atelier'"
    )[0][0]
    assert apres == utilises


def test_valeur_d_attribut_utilisee_garde_le_composant_modifiable(
    app: FastAPI, range_: TestClient
) -> None:
    """Point 3 du débat : valeur utilisée hors référence, puis autre attribut modifié → 200."""
    longueur = {"libelle": "Longueur", "type": "nombre"}
    assert range_.post(f"/p/{REF}/api/attributs", json=longueur).status_code == 201
    creer_projet(range_)
    ranger(app, "beta", {"dossier": None})
    beta = "/p/beta/api"
    assert (
        range_.post(f"{beta}/attributs", json={"libelle": "Matière", "type": "liste"}).status_code
        == 201
    )
    assert (
        range_.post(f"{beta}/attributs/matiere/valeurs", json={"libelle": "Inox"}).status_code
        == 201
    )
    assert (
        range_.post(f"{beta}/attributs", json={"libelle": "Masse", "type": "nombre"}).status_code
        == 201
    )
    bloc = {"code": "TST", "nom": "Essais"}
    assert range_.post(f"{beta}/blocs", json=bloc).status_code == 201
    composant = {
        "bloc_code": "TST",
        "fonction": "Fixation",
        "designation": "Équerre",
        "qte_besoin": 1,
        "mode_appro": "Achat",
    }
    cree = range_.post(f"{beta}/composants", json=composant)
    assert cree.status_code == 201, cree.text
    ident = cree.json()["id"]
    assert (
        range_.put(
            f"{beta}/composants/{ident}/attributs", json={"valeurs": {"matiere": "Inox"}}
        ).status_code
        == 200
    )
    rapport = ranger(app, "beta", {"dossier": "spoc"})["propagation"]
    assert any("Inox" in s for s in rapport["signalements"])
    assert lire(app, "beta", "SELECT actif FROM attribut_valeur WHERE code = 'Inox'") == [(0,)]
    reponse = range_.put(
        f"{beta}/composants/{ident}/attributs", json={"valeurs": {"longueur": 2.5}}
    )
    assert reponse.status_code == 200, reponse.text
    assert lire(
        app, "beta", "SELECT valeur_texte FROM composant_attribut WHERE attribut_code = 'matiere'"
    ) == [("Inox",)]


# --- 5. Verrou : réglages imposés refusés, réglages locaux libres --------------------------------


IMPOSEES = [
    ("POST", "/api/blocs", {"code": "NEUF", "nom": "Neuf"}),
    ("PATCH", "/api/blocs/ALI", {"nom": "Autre nom"}),
    ("POST", "/api/listes/criticite", {"libelle": "Moyenne"}),
    ("POST", "/api/listes/type_frais", {"libelle": "Emballage"}),
    ("POST", "/api/attributs", {"libelle": "Couleur", "type": "texte"}),
    ("PATCH", "/api/parametres", {"taux_tva_defaut": 0.1}),
    ("PATCH", "/api/parametres", {"etablissement_nom": "Autre"}),
    ("PATCH", "/api/parametres", {"budget_ht": 1}),
    ("PATCH", "/api/parametres", {"prefixe_id": "AUTRE"}),
    ("DELETE", "/api/parametres/logo", None),
]
LOCALES = [
    ("PATCH", "/api/blocs/ALI", {"budget_cible_ht": 500, "responsable": "Chef"}),
    ("POST", "/api/listes/statut_choix", {"libelle": "À revoir"}),
    ("POST", "/api/listes/statut_appro", {"libelle": "Relancé"}),
]


def test_reglages_imposes_refuses_locaux_libres(app: FastAPI, range_: TestClient) -> None:
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    avant = empreinte(app, PROJET)
    for methode, adresse, corps in IMPOSEES:
        reponse = admin.request(methode, f"/p/{PROJET}{adresse}", json=corps)
        assert reponse.status_code in (403, 404, 409), (adresse, corps, reponse.status_code)
    assert empreinte(app, PROJET) == avant
    for methode, adresse, corps in LOCALES:
        reponse = admin.request(methode, f"/p/{PROJET}{adresse}", json=corps)
        assert reponse.status_code < 300, (adresse, reponse.text)


TABLES_SQL = [
    "INSERT INTO bloc (code, nom) VALUES ('ZZ', 'Z')",
    "UPDATE bloc SET nom = 'Z' WHERE code = 'ALI'",
    "DELETE FROM valeur_liste WHERE liste = 'type_frais'",
    "INSERT INTO valeur_liste (liste, code, libelle) VALUES ('criticite', 'Z', 'Z')",
    "INSERT INTO attribut (code, libelle, type) VALUES ('z', 'Z', 'texte')",
    "UPDATE parametre SET valeur = '0.1' WHERE cle = 'taux_tva_defaut'",
    "INSERT INTO parametre (cle, valeur) VALUES ('etablissement_nom', 'Z')"
    " ON CONFLICT (cle) DO UPDATE SET valeur = 'Z'",
    "DELETE FROM logo",
]


@pytest.mark.parametrize("requete", TABLES_SQL)
def test_verrou_en_base(app: FastAPI, range_: TestClient, requete: str) -> None:
    """Point 5 du débat : même une écriture SQL directe est refusée."""
    conn = db.connect(base(app, PROJET), creer=False)
    try:
        if "logo" in requete:
            conn.execute("UPDATE reglages_imposes SET propagation = 1")
            conn.execute(
                "INSERT INTO logo VALUES (1, 'image/png', x'00', 1, 1, '2026-01-01T00:00:00')"
            )
            conn.execute("UPDATE reglages_imposes SET propagation = 0")
        with pytest.raises(sqlite3.IntegrityError, match="imposé par le dossier"):
            conn.execute(requete)
    finally:
        conn.close()


def test_projet_sorti_du_dossier_libre(app: FastAPI, range_: TestClient) -> None:
    ranger(app, PROJET, {"dossier": None})
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    assert (
        admin.post(f"/p/{PROJET}/api/blocs", json={"code": "NEUF", "nom": "Neuf"}).status_code
        == 201
    )


# --- 6. Import ------------------------------------------------------------------------------


def test_import_refuse_une_valeur_de_liste_imposee(app: FastAPI, range_: TestClient) -> None:
    conn = db.connect(base(app, PROJET), creer=False)
    try:
        entite = {"type": "valeur_liste", "liste": "criticite", "code": "Neuve", "libelle": "Neuve"}
        with pytest.raises(import_application.LigneRefusee, match="imposée par le dossier"):
            import_application._creer_entite(conn, entite, None)
        locale = {
            "type": "valeur_liste",
            "liste": "statut_choix",
            "code": "Neuf",
            "libelle": "Neuf",
        }
        with db.transaction(conn):
            assert import_application._creer_entite(conn, locale, None) is True
    finally:
        conn.close()


# --- 7. Propagation interrompue, reprise -------------------------------------------------------


def test_propagation_interrompue_puis_reprise(
    app: FastAPI, range_: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    creer_projet(range_)
    vraie = propagation.synchroniser

    def panne(projet: Path, *args: object, **kwargs: object) -> propagation.Rapport:
        if projet.parent.name == "beta":
            raise sqlite3.OperationalError("panne simulée")
        return vraie(projet, *args, **kwargs)

    monkeypatch.setattr(propagation, "synchroniser", panne)
    assert range_.patch(f"/p/{REF}/api/blocs/ALI", json={"nom": "Alim."}).status_code == 200
    conn = _comptes(app)
    try:
        etat = reference.etat_des_projets(conn, app.state.registre, "spoc")
        assert etat == {PROJET: True, "beta": False}
        monkeypatch.setattr(propagation, "synchroniser", vraie)
        reference.reprendre(
            conn, app.state.registre, (app.state.dossier_data, app.state.dossier_echange)
        )
        assert reference.etat_des_projets(conn, app.state.registre, "spoc") == {
            PROJET: True,
            "beta": True,
        }
    finally:
        conn.close()
    avant = nb_journal(app, "beta")
    conn = _comptes(app)
    try:
        reference.propager(conn, app.state.registre, "spoc")
    finally:
        conn.close()
    assert nb_journal(app, "beta") == avant


# --- 8. Budget fixé par le dossier --------------------------------------------------------------


def test_budget_fixe_depuis_le_dossier(app: FastAPI, range_: TestClient) -> None:
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    gestion = connecter(app, "gestion@ecole.test")
    assert gestion.patch(f"/api/projets/{PROJET}", json={"budget_ht": 5000}).status_code == 200
    assert lire(app, PROJET, "SELECT valeur FROM parametre WHERE cle = 'budget_ht'") == [
        ("5000.0",)
    ]
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    assert admin.patch(f"/api/projets/{PROJET}", json={"budget_ht": 1}).status_code == 403


# --- 9. La référence n'est pas un projet comme les autres ---------------------------------------


def test_reference_cachee_et_reservee(app: FastAPI, range_: TestClient) -> None:
    codes = {
        c["code"]
        for o in range_.get("/api/accueil").json()["organismes"]
        for d in o["dossiers"]
        for c in d["projets"]
    }
    assert REF not in codes
    assert range_.get(f"/p/{REF}/api/composants").status_code == 404
    assert range_.get(f"/p/{REF}/api/blocs").status_code == 200
    creer_compte(app, "membre@ecole.test", "administrateur")
    membre = connecter(app, "membre@ecole.test")
    assert membre.get(f"/p/{REF}/api/blocs").status_code == 403
    assert range_.patch(f"/api/projets/{REF}", json={"dossier": None}).status_code == 403
    corps = {"code": "ref-x", "nom_equipe": "X", "prefixe_id": "X"}
    assert range_.post("/api/dossiers/spoc/projets", json=corps).status_code == 400


# --- Conflits au rangement d'un second projet (point 4 du débat) -------------------------------


def test_rangement_refuse_sur_conflit_de_type(app: FastAPI, range_: TestClient) -> None:
    assert (
        range_.post(
            f"/p/{REF}/api/attributs", json={"libelle": "Tension", "type": "nombre"}
        ).status_code
        == 201
    )
    creer_projet(range_)
    ranger(app, "beta", {"dossier": None})
    conn = db.connect(base(app, "beta"), creer=False)
    try:
        with db.transaction(conn):
            conn.execute("UPDATE attribut SET type = 'texte' WHERE code = 'tension'")
    finally:
        conn.close()
    avant = contenu(base(app, "beta"))
    reponse = range_.patch("/api/projets/beta", json={"dossier": "spoc"})
    assert reponse.status_code == 409
    assert "tension" in reponse.json()["erreur"]
    assert contenu(base(app, "beta")) == avant


# --- 15b-3 : nouveau projet repris d'un modèle ---------------------------------------------------

LISTES_LOCALES = (
    "SELECT liste, code, libelle, ordre, actif FROM valeur_liste"
    " WHERE liste IN ('statut_appro', 'statut_choix') ORDER BY liste, code"
)
ENSEMBLES = "SELECT code, nom, ordre, parent_code, description FROM ensemble ORDER BY code"


def test_projet_repris_d_un_modele(app: FastAPI, range_: TestClient) -> None:
    conn = db.connect(base(app, PROJET), creer=False)
    try:
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO ensemble (code, nom, ordre, parent_code, responsable, budget_cible_ht,"
                " statut_montage, archive) VALUES"
                " ('ROUE', 'Roue', 2, NULL, 'Chef', 10, 'Monte', 0),"
                " ('CHASSIS', 'Châssis', 1, NULL, 'Chef', 20, 'En cours', 0),"
                " ('VIEUX', 'Ancien', 3, NULL, NULL, NULL, 'Non commence', 1)"
            )
            conn.execute("UPDATE ensemble SET parent_code = 'CHASSIS' WHERE code = 'ROUE'")
            conn.execute(
                "INSERT INTO valeur_liste (liste, code, libelle, ordre) VALUES"
                " ('statut_choix', 'A revoir', 'À revoir', 9)"
            )
    finally:
        conn.close()
    corps = {"code": "beta", "nom_equipe": "Beta", "prefixe_id": "BET", "modele": PROJET}
    assert range_.post("/api/dossiers/spoc/projets", json=corps).status_code == 201
    actifs = (
        "SELECT code, nom, ordre, parent_code, description FROM ensemble WHERE archive = 0"
        " ORDER BY code"
    )
    assert lire(app, "beta", ENSEMBLES) == lire(app, PROJET, actifs)
    assert len(lire(app, "beta", ENSEMBLES)) > 0
    assert lire(app, "beta", LISTES_LOCALES) == lire(app, PROJET, LISTES_LOCALES)
    # Rien de l'équipe du modèle : ni composants, ni affectations, ni responsables, ni budgets.
    for requete in (
        "SELECT COUNT(*) FROM composant",
        "SELECT COUNT(*) FROM affectation",
        "SELECT COUNT(*) FROM commande",
        "SELECT COUNT(*) FROM ensemble"
        " WHERE responsable IS NOT NULL OR budget_cible_ht IS NOT NULL",
        "SELECT COUNT(*) FROM ensemble WHERE statut_montage <> 'Non commence'",
    ):
        assert lire(app, "beta", requete) == [(0,)], requete
    assert empreinte(app, "beta") == empreinte(app, REF)


def test_modele_d_un_autre_dossier_refuse(
    app: FastAPI, range_: TestClient, dossier_data: Path
) -> None:
    creer_dossier(app, "meca", {"code": "autre", "nom": "Autre"})
    corps = {"code": "gamma", "nom_equipe": "Gamma", "prefixe_id": "GAM", "modele": PROJET}
    reponse = range_.post("/api/dossiers/autre/projets", json=corps)
    assert reponse.status_code == 400
    assert not (dossier_data / "projets" / "gamma").exists()
    corps["modele"] = "inconnu"
    assert range_.post("/api/dossiers/autre/projets", json=corps).status_code == 404
