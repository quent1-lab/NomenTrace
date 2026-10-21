"""Hiérarchie organisme › dossier › projet, droits hérités, accueil, création de projet (15b-1).

Deux organismes : « meca » (dossier « spoc », où est rangé le projet du jeu d'essai) et
« autre » (dossier « autre-dossier »). Chaque test vérifie qu'un droit ne déborde jamais
sur un autre organisme ni sur un projet hors dossier.
"""

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from backend.services import authentification, comptes, droits, hierarchie, projets
from tests.test_comptes import MOT_DE_PASSE, PROJET, connecter, creer_compte, navigateur

SERVEUR = droits.UTILISATEUR_LOCAL


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
        _structure(application)
        yield application


def _comptes(app: FastAPI) -> sqlite3.Connection:
    return db.connect(app.state.chemin_comptes)


def creer_dossier(app: FastAPI, organisme: str, valeurs: dict) -> None:
    """Dossier et sa référence, mise en ligne comme le fait la route."""
    conn = _comptes(app)
    try:
        etat = app.state
        _, emp = hierarchie.create_dossier(
            conn, SERVEUR, organisme, valeurs, (etat.dossier_data, etat.dossier_echange)
        )
        etat.registre.references.add(emp.code)
        projets.mettre_en_ligne(etat.registre, etat.exports, emp)
    finally:
        conn.close()


def ranger(app: FastAPI, code: str, modifs: dict) -> dict:
    conn = _comptes(app)
    try:
        return hierarchie.patch_projet(conn, SERVEUR, code, modifs, app.state.registre)
    finally:
        conn.close()


def creer_organisme(app: FastAPI, code: str, nom: str) -> None:
    """Organisme et sa référence (liste des fournisseurs), mise en ligne comme le fait la route."""
    conn = _comptes(app)
    try:
        etat = app.state
        _, emp = hierarchie.create_organisme(
            conn, SERVEUR, code, nom, (etat.dossier_data, etat.dossier_echange)
        )
        etat.registre.references.add(emp.code)
        projets.mettre_en_ligne(etat.registre, etat.exports, emp)
    finally:
        conn.close()


def _structure(app: FastAPI) -> None:
    creer_organisme(app, "meca", "Mécatronique")
    creer_organisme(app, "autre", "Autre école")
    creer_dossier(app, "meca", {"code": "spoc", "nom": "SPOC 2027", "nom_projet": "SPOC"})
    ranger(app, PROJET, {"dossier": "spoc", "nom_equipe": "Alpha"})
    creer_dossier(app, "autre", {"code": "autre-dossier", "nom": "Autre"})


def membre_organisme(app: FastAPI, identifiant: str, organisme: str, profil: str) -> int:
    """Compte qui n'a qu'un profil d'organisme, mot de passe choisi."""
    conn = _comptes(app)
    try:
        cree = hierarchie.invite_membre(
            conn,
            SERVEUR,
            organisme,
            {"identifiant": identifiant, "nom": identifiant.split("@")[0], "profil": profil},
        )
        if "jeton" in cree:
            comptes.accept_invitation(conn, cree["jeton"], MOT_DE_PASSE)
        return int(cree["id"])
    finally:
        conn.close()


def serveur(app: FastAPI) -> TestClient:
    conn = _comptes(app)
    try:
        cree = comptes.ensure_admin_serveur(conn, "serveur@ecole.test", "serveur")
        comptes.accept_invitation(conn, cree["jeton"], MOT_DE_PASSE)
    finally:
        conn.close()
    return connecter(app, "serveur@ecole.test")


def creer_projet(client: TestClient, code: str = "beta", dossier: str = "spoc") -> dict:
    corps = {"code": code, "nom_equipe": code.capitalize(), "prefixe_id": "BET"}
    reponse = client.post(f"/api/dossiers/{dossier}/projets", json=corps)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


# --- 1. Rôle effectif ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profil", "direct", "role", "tous_blocs", "permissions"),
    [
        ("gestion", None, "administrateur", False, set()),
        ("lecture", None, "lecteur", False, set()),
        ("achats_stock", None, "contributeur", True, {"achats"}),
        ("achats_stock", "contributeur", "contributeur", True, {"achats", "ensembles"}),
        ("lecture", "contributeur", "contributeur", False, {"ensembles"}),
        ("achats_stock", "administrateur", "administrateur", True, {"achats", "ensembles"}),
    ],
)
def test_role_effectif(
    app: FastAPI,
    profil: str,
    direct: str | None,
    role: str,
    tous_blocs: bool,
    permissions: set[str],
) -> None:
    id_ = membre_organisme(app, "membre@ecole.test", "meca", profil)
    conn = _comptes(app)
    try:
        if direct:
            comptes.create_utilisateur(
                conn,
                PROJET,
                {
                    "identifiant": "membre@ecole.test",
                    "nom": "membre",
                    "role": direct,
                    "blocs": ["IHM"],
                    "permissions": ["ensembles"],
                },
                "test",
            )
        effectif = comptes.get_utilisateur(conn, id_, PROJET)
    finally:
        conn.close()
    assert effectif.role == role
    assert effectif.tous_blocs is tous_blocs
    assert effectif.permissions == permissions


def test_profil_d_un_autre_organisme_n_ouvre_rien(app: FastAPI) -> None:
    id_ = membre_organisme(app, "ailleurs@ecole.test", "autre", "gestion")
    conn = _comptes(app)
    try:
        assert comptes.get_utilisateur(conn, id_, PROJET).role is None
    finally:
        conn.close()
    client = connecter(app, "ailleurs@ecole.test")
    assert client.get(f"/p/{PROJET}/api/composants").status_code == 403


def test_profil_ne_vaut_pas_hors_dossier(app: FastAPI) -> None:
    id_ = membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    ranger(app, PROJET, {"dossier": None})
    conn = _comptes(app)
    try:
        assert comptes.get_utilisateur(conn, id_, PROJET).role is None
    finally:
        conn.close()


def test_achats_stock_ecrit_dans_tous_les_blocs(app: FastAPI) -> None:
    membre_organisme(app, "achats@ecole.test", "meca", "achats_stock")
    client = connecter(app, "achats@ecole.test")
    for composant in ("ESSAI-ALI-001", "ESSAI-IHM-001"):
        reponse = client.patch(f"/p/{PROJET}/api/composants/{composant}", json={"pu_releve": 3.5})
        assert reponse.status_code == 200, reponse.text
    session = client.get(f"/p/{PROJET}/api/session").json()["utilisateur"]
    assert session["tous_blocs"] is True
    assert client.get(f"/p/{PROJET}/api/utilisateurs").status_code == 403


def test_lecture_d_organisme_ne_modifie_rien(app: FastAPI) -> None:
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    client = connecter(app, "lecture@ecole.test")
    assert client.get(f"/p/{PROJET}/api/composants").status_code == 200
    reponse = client.patch(f"/p/{PROJET}/api/composants/ESSAI-ALI-001", json={"pu_releve": 1})
    assert reponse.status_code == 403


def test_gestion_administre_les_projets_de_l_organisme(app: FastAPI) -> None:
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    client = connecter(app, "gestion@ecole.test")
    assert client.get(f"/p/{PROJET}/api/utilisateurs").status_code == 200


# --- 2. Connexion commune -----------------------------------------------------------------------


def test_connexion_avec_un_profil_d_organisme_seul(app: FastAPI) -> None:
    """Profil dans un organisme qui ne contient pas le projet de l'instance."""
    membre_organisme(app, "lecture@ecole.test", "autre", "lecture")
    connecter(app, "lecture@ecole.test")


def test_connexion_et_accueil_projet_de_l_instance_hors_ligne(app: FastAPI) -> None:
    """Point 5 du débat : la connexion n'ouvre aucune base de projet."""
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    app.state.registre.hors_ligne[PROJET] = "test"
    del app.state.registre.projets[PROJET]
    client = connecter(app, "gestion@ecole.test")
    assert client.get("/api/accueil").status_code == 200
    creer_projet(client)


# --- 3. Accueil ---------------------------------------------------------------------------------


def _codes(accueil: dict) -> set[str]:
    codes = {c["code"] for c in accueil["hors_dossier"]}
    for org in accueil["organismes"]:
        for dos in org["dossiers"]:
            codes |= {c["code"] for c in dos["projets"]}
    return codes


def test_accueil_membre_d_un_seul_projet(app: FastAPI) -> None:
    creer_compte(app, "seul@ecole.test", "lecteur")
    accueil = connecter(app, "seul@ecole.test").get("/api/accueil").json()
    assert accueil["destination"] == f"/p/{PROJET}/"
    assert _codes(accueil) == {PROJET}


def test_accueil_selon_le_role(app: FastAPI) -> None:
    administrateur = serveur(app)
    creer_projet(administrateur, "beta", "spoc")
    creer_projet(administrateur, "gamma", "autre-dossier")
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    accueil = connecter(app, "lecture@ecole.test").get("/api/accueil").json()
    assert _codes(accueil) == {PROJET, "beta"}
    assert accueil["destination"] is None
    assert {o["code"] for o in accueil["organismes"]} == {"meca"}
    tout = administrateur.get("/api/accueil").json()
    assert _codes(tout) == {PROJET, "beta", "gamma"}


def test_accueil_du_responsable_achats(app: FastAPI) -> None:
    administrateur = serveur(app)
    creer_projet(administrateur, "beta", "spoc")
    id_ = creer_compte(app, "resp@ecole.test", "contributeur", blocs=("IHM",))
    assert (
        administrateur.post(
            "/api/dossiers/spoc/responsables", json={"utilisateur_id": id_}
        ).status_code
        == 201
    )
    client = connecter(app, "resp@ecole.test")
    accueil = client.get("/api/accueil").json()
    cartes = {
        c["code"]: c for o in accueil["organismes"] for d in o["dossiers"] for c in d["projets"]
    }
    assert set(cartes) == {PROJET, "beta"}
    assert cartes[PROJET]["acces"] == "contributeur"
    assert cartes["beta"]["acces"] is None
    assert cartes["beta"]["resume"] is not None
    # 4. Le résumé ne donne aucun accès au détail.
    assert client.get("/p/beta/api/composants").status_code == 403
    assert client.get("/api/dossiers/spoc").status_code == 200


def test_accueil_projet_hors_ligne_marque(app: FastAPI) -> None:
    """Point 8 du débat : un projet hors ligne ne fait pas tomber l'accueil."""
    administrateur = serveur(app)
    app.state.registre.hors_ligne[PROJET] = "test"
    del app.state.registre.projets[PROJET]
    accueil = administrateur.get("/api/accueil").json()
    carte = accueil["organismes"][1]["dossiers"][0]["projets"][0]
    assert carte["code"] == PROJET
    assert carte["hors_ligne"] is True
    assert carte["resume"] is None


def test_accueil_serveur_voit_les_projets_hors_dossier(app: FastAPI) -> None:
    administrateur = serveur(app)
    ranger(app, PROJET, {"dossier": None})
    accueil = administrateur.get("/api/accueil").json()
    assert [c["code"] for c in accueil["hors_dossier"]] == [PROJET]


# --- 5. Création d'un projet --------------------------------------------------------------------


def test_creation_d_un_projet_sans_redemarrage(app: FastAPI, dossier_data: Path) -> None:
    administrateur = serveur(app)
    creer_projet(administrateur)
    assert administrateur.get("/p/beta/api/sante").status_code == 200
    reglages = administrateur.get("/p/beta/api/parametres").json()
    # 15b-2 : le projet rangé le premier a donné la référence, son nom compris.
    assert reglages["nom_projet"] == "Projet d'essai"
    assert reglages["prefixe_id"] == "BET"
    signalements: list[str] = []
    app.state.exports["beta"].signaler = lambda: signalements.append("beta")
    ensemble = {"code": "CHASSIS", "nom": "Châssis"}
    assert administrateur.post("/p/beta/api/ensembles", json=ensemble).status_code == 201
    assert signalements == ["beta"]
    assert (dossier_data / "projets" / "beta" / "nomentrace.db").is_file()


def _contenu(dossier: Path) -> set[Path]:
    return {chemin for chemin in dossier.rglob("*") if "sauvegardes" not in chemin.parts}


@pytest.mark.parametrize(
    ("code", "statut"), [(PROJET, 409), ("Maj", 422), ("a/b", 422), ("deja", 409)]
)
def test_creation_refusee_sans_trace(
    app: FastAPI, dossier_data: Path, code: str, statut: int
) -> None:
    administrateur = serveur(app)
    (dossier_data / "projets" / "deja").mkdir(parents=True)
    avant = _contenu(dossier_data)
    corps = {"code": code, "nom_equipe": "X", "prefixe_id": "X"}
    reponse = administrateur.post("/api/dossiers/spoc/projets", json=corps)
    assert reponse.status_code == statut
    assert _contenu(dossier_data) == avant


def test_creation_reservee_a_la_gestion(app: FastAPI) -> None:
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    client = connecter(app, "lecture@ecole.test")
    corps = {"code": "beta", "nom_equipe": "Beta", "prefixe_id": "BET"}
    assert client.post("/api/dossiers/spoc/projets", json=corps).status_code == 403


def test_creation_interrompue_ne_laisse_rien(
    app: FastAPI, dossier_data: Path, dossier_echange: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point 6 du débat : échec à l'inscription, puis création rejouée."""
    administrateur = serveur(app)
    inscrire = projets._inscrire_nouveau

    def panne(*_: object) -> None:
        raise sqlite3.OperationalError("panne simulée")

    monkeypatch.setattr(projets, "_inscrire_nouveau", panne)
    corps = {"code": "beta", "nom_equipe": "Beta", "prefixe_id": "BET"}
    with pytest.raises(sqlite3.OperationalError):
        administrateur.post("/api/dossiers/spoc/projets", json=corps)
    for reste in (
        dossier_data / "projets" / "beta",
        dossier_data / "projets" / ".creation-beta",
        dossier_echange / "projets" / "beta",
    ):
        assert not reste.exists(), reste
    monkeypatch.setattr(projets, "_inscrire_nouveau", inscrire)
    creer_projet(administrateur)


def test_creations_simultanees_du_meme_code(app: FastAPI) -> None:
    administrateur = serveur(app)
    corps = {"code": "beta", "nom_equipe": "Beta", "prefixe_id": "BET"}
    statuts: list[int] = []

    def creer() -> None:
        statuts.append(administrateur.post("/api/dossiers/spoc/projets", json=corps).status_code)

    fils = [threading.Thread(target=creer) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    assert sorted(statuts) == [201, 409]


def test_creation_avec_un_administrateur_existant(app: FastAPI) -> None:
    """Point 2 du débat : un compte existant reçoit l'accès, sans nouveau lien."""
    administrateur = serveur(app)
    creer_compte(app, "chef@ecole.test", "lecteur")
    corps = {
        "code": "beta",
        "nom_equipe": "Beta",
        "prefixe_id": "BET",
        "admin_identifiant": "chef@ecole.test",
    }
    reponse = administrateur.post("/api/dossiers/spoc/projets", json=corps)
    assert reponse.status_code == 201, reponse.text
    assert reponse.json()["invitation"]["existant"] is True
    chef = connecter(app, "chef@ecole.test")
    assert chef.get("/p/beta/api/utilisateurs").status_code == 200


# --- Points du débat : identité des comptes partagés, invitations, périmètre --------------------


def test_admin_de_projet_ne_reprend_pas_un_compte_partage(app: FastAPI) -> None:
    """Point 1 : relancer l'invitation ou désactiver un compte d'organisme → 403."""
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    id_ = membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    conn = _comptes(app)
    try:
        comptes.create_utilisateur(
            conn,
            PROJET,
            {"identifiant": "gestion@ecole.test", "nom": "gestion", "role": "lecteur"},
            "test",
        )
    finally:
        conn.close()
    assert admin.post(f"/p/{PROJET}/api/utilisateurs/{id_}/invitation").status_code == 403
    assert (
        admin.patch(f"/p/{PROJET}/api/utilisateurs/{id_}", json={"actif": False}).status_code == 403
    )
    # Son rôle dans le projet reste réglable, et il peut être retiré du projet.
    assert (
        admin.patch(
            f"/p/{PROJET}/api/utilisateurs/{id_}", json={"role": "contributeur"}
        ).status_code
        == 200
    )
    assert admin.delete(f"/p/{PROJET}/api/utilisateurs/{id_}").status_code == 200
    connecter(app, "gestion@ecole.test")


def test_ecran_utilisateurs_ne_recopie_pas_les_droits_herites(app: FastAPI) -> None:
    """Point 4 : PATCH sans changement, puis retrait du profil → rôle direct seul."""
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin = connecter(app, "admin@ecole.test")
    id_ = membre_organisme(app, "achats@ecole.test", "meca", "achats_stock")
    conn = _comptes(app)
    try:
        comptes.create_utilisateur(
            conn,
            PROJET,
            {"identifiant": "achats@ecole.test", "nom": "achats", "role": "lecteur"},
            "test",
        )
    finally:
        conn.close()
    ligne = next(u for u in admin.get(f"/p/{PROJET}/api/utilisateurs").json() if u["id"] == id_)
    assert (ligne["role"], ligne["permissions"]) == ("lecteur", [])
    corps = {k: ligne[k] for k in ("role", "blocs", "permissions")}
    assert admin.patch(f"/p/{PROJET}/api/utilisateurs/{id_}", json=corps).status_code == 200
    conn = _comptes(app)
    try:
        hierarchie.retirer_membre(conn, SERVEUR, "meca", id_)
        effectif = comptes.get_utilisateur(conn, id_, PROJET)
    finally:
        conn.close()
    assert (effectif.role, effectif.permissions, effectif.tous_blocs) == (
        "lecteur",
        frozenset(),
        False,
    )


def test_invitations_par_niveau(app: FastAPI) -> None:
    """Point 2 : qui accorde un profil d'organisme, et où."""
    creer_compte(app, "admin@ecole.test", "administrateur")
    admin_projet = connecter(app, "admin@ecole.test")
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    gestion = connecter(app, "gestion@ecole.test")
    corps = {"identifiant": "nouveau@ecole.test", "nom": "nouveau", "profil": "lecture"}
    assert admin_projet.post("/api/organismes/meca/membres", json=corps).status_code == 403
    assert gestion.post("/api/organismes/autre/membres", json=corps).status_code == 403
    cree = gestion.post("/api/organismes/meca/membres", json=corps)
    assert cree.status_code == 201
    assert "jeton" in cree.json()
    existant = {"identifiant": "admin@ecole.test", "nom": "admin", "profil": "lecture"}
    reponse = gestion.post("/api/organismes/meca/membres", json=existant)
    assert reponse.status_code == 201
    assert "jeton" not in reponse.json()


ROUTES_HIERARCHIE = [
    ("GET", "/api/organismes/autre", None),
    ("PATCH", "/api/organismes/autre", {"nom": "Pris"}),
    ("POST", "/api/organismes/autre/dossiers", {"code": "x", "nom": "X"}),
    (
        "POST",
        "/api/organismes/autre/membres",
        {"identifiant": "a@b.fr", "nom": "a", "profil": "lecture"},
    ),
    ("GET", "/api/dossiers/autre-dossier", None),
    ("PATCH", "/api/dossiers/autre-dossier", {"nom": "Pris"}),
    (
        "POST",
        "/api/dossiers/autre-dossier/projets",
        {"code": "x", "nom_equipe": "X", "prefixe_id": "X"},
    ),
    ("POST", "/api/dossiers/autre-dossier/responsables", {"utilisateur_id": 1}),
    ("POST", "/api/organismes", {"code": "neuf", "nom": "Neuf"}),
    ("PATCH", f"/api/projets/{PROJET}", {"dossier": None}),
]


@pytest.mark.parametrize(("methode", "adresse", "corps"), ROUTES_HIERARCHIE)
def test_gestion_ne_deborde_pas_de_son_organisme(
    app: FastAPI, methode: str, adresse: str, corps: dict | None
) -> None:
    """Point 3 : chaque route commune, visée sur un autre organisme ou réservée au serveur."""
    membre_organisme(app, "gestion@ecole.test", "meca", "gestion")
    client = connecter(app, "gestion@ecole.test")
    for prefixe in ("", f"/p/{PROJET}"):
        reponse = client.request(methode, prefixe + adresse, json=corps)
        assert reponse.status_code == 403, (prefixe, reponse.text)


def test_routes_communes_exigent_une_connexion(app: FastAPI) -> None:
    client = navigateur(app)
    assert client.get("/api/accueil").status_code == 401
    assert client.post("/api/organismes", json={"code": "x", "nom": "X"}).status_code == 401


# --- 6. Migration de la base commune ------------------------------------------------------------


def test_migration_004_garde_les_acces(tmp_path: Path) -> None:
    from backend import config

    anciennes = tmp_path / "migrations"
    anciennes.mkdir()
    for fichier in sorted(config.DOSSIER_MIGRATIONS_COMPTES.glob("00[1-3]_*.sql")):
        (anciennes / fichier.name).write_text(fichier.read_text(encoding="utf-8"), encoding="utf-8")
    chemin = tmp_path / "comptes.db"
    conn = db.connect(chemin)
    try:
        db.apply_migrations(conn, anciennes)
        conn.execute("INSERT INTO utilisateur (identifiant, nom) VALUES ('a@b.fr', 'a')")
        conn.execute("INSERT INTO projet (code) VALUES ('principal')")
        conn.execute("INSERT INTO acces VALUES (1, 'principal', 'administrateur')")
        assert db.apply_migrations(conn, config.DOSSIER_MIGRATIONS_COMPTES) >= 4
        assert comptes.get_utilisateur(conn, 1, "principal").role == "administrateur"
        ligne = conn.execute("SELECT dossier, nom_equipe FROM projet").fetchone()
        assert tuple(ligne) == (None, None)
    finally:
        conn.close()


# --- 7. Mode local ------------------------------------------------------------------------------


def test_mode_local_multi_projet(client: TestClient) -> None:
    accueil = client.get("/api/accueil").json()
    assert accueil["compte"]["admin_serveur"] is True
    assert accueil["destination"] is not None  # un seul projet, aucune structure
    assert (
        client.post("/api/organismes", json={"code": "meca", "nom": "Mécatronique"}).status_code
        == 201
    )
    dossier = {"code": "spoc", "nom": "SPOC 2027", "nom_projet": "SPOC"}
    assert client.post("/api/organismes/meca/dossiers", json=dossier).status_code == 201
    creer_projet(client)
    accueil = client.get("/api/accueil").json()
    assert accueil["destination"] is None
    assert "beta" in _codes(accueil)
    assert client.get("/p/beta/api/composants").status_code == 200


# --- 8. Adresses --------------------------------------------------------------------------------


def test_pages_communes_servies(client: TestClient) -> None:
    for adresse in ("/", "/d/spoc/", "/o/meca/"):
        reponse = client.get(adresse, follow_redirects=False)
        assert reponse.status_code == 200, adresse
        assert "/js/accueil.js" in reponse.text
    assert client.get("/d/spoc", follow_redirects=False).headers["location"] == "/d/spoc/"
    for adresse in ("/d/Maj/", "/o/a.b/", "/d/x/y"):
        assert client.get(adresse, follow_redirects=False).status_code == 404, adresse


# --- Restauration (point 7 du débat) ------------------------------------------------------------


def test_restauration_garde_le_rangement_des_projets(
    app: FastAPI, dossier_data: Path, dossier_echange: Path
) -> None:
    """Archive prise avant la création d'un projet : il reste rangé après restauration."""
    from backend.services import restauration, sauvegardes

    emp = app.state.registre.projets[PROJET]
    archive = sauvegardes.build_archive_serveur(
        app.state.chemin_comptes, [(PROJET, emp.base, emp.documents)]
    )
    administrateur = serveur(app)
    creer_projet(administrateur)
    cible = restauration.Cible(
        app.state.chemin_comptes, dossier_data, dossier_echange, dossier_data / "nomentrace.db"
    )
    restauration.restore_archive(archive, cible, PROJET)
    conn = _comptes(app)
    try:
        lignes = {
            r["code"]: (r["dossier"], r["nom_equipe"])
            for r in conn.execute("SELECT * FROM projet WHERE reference = 0")
        }
    finally:
        conn.close()
    assert lignes == {PROJET: ("spoc", "Alpha"), "beta": ("spoc", "Beta")}
