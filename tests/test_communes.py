"""Commandes communes à un dossier (phase 16a).

Le projet du jeu d'essai (« essai », équipe Alpha) et un projet « beta » sont rangés dans le
dossier « epreuve » de l'organisme « meca ». Les grandeurs suivies : la part de chaque projet
(frais, estimé, réel) écrite dans sa copie, au bit près pour le réel ; la version de la copie ;
le refus de toute écriture locale sur une copie, voie par voie.

Exemple de référence (réponse de l'utilisateur, 2026-10-21) : A 300 € de lignes, B 100 €,
livraison 20 €, réel 410 € → A 410 × 310/420 = 302,62 €, B 107,38 €.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import db
from backend.main import create_app
from backend.services import authentification, communes, communes_sync
from tests.test_comptes import PROJET, connecter, creer_compte, navigateur
from tests.test_fournisseurs_communs import composant
from tests.test_hierarchie import (
    _comptes,
    creer_dossier,
    creer_organisme,
    creer_projet,
    membre_organisme,
    ranger,
    serveur,
)
from tests.test_reference import base, lire

URL = "/api/dossiers/epreuve/communes"
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
        creer_dossier(application, "meca", {"code": "epreuve", "nom": "Épreuve 2027"})
        yield application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Deux projets rangés et un administrateur du serveur connecté."""
    ranger(app, PROJET, {"dossier": "epreuve", "nom_equipe": "Alpha"})
    serveur_ = serveur(app)
    creer_projet(serveur_)
    return serveur_


def nouvelle(client: TestClient, **valeurs: object) -> str:
    reponse = client.post(URL, json={"fournisseur_nom": "Farnell", **valeurs})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()["numero"]


def ajouter(client: TestClient, numero: str, lignes: list[dict]) -> dict:
    reponse = client.post(f"{URL}/{numero}/lignes", json={"lignes": lignes})
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def ligne(projet: str, composant_id: str, qte: int, pu: float | None) -> dict:
    return {"projet": projet, "composant_id": composant_id, "qte_commandee": qte, "pu_ht_devis": pu}


@pytest.fixture
def exemple(client: TestClient) -> str:
    """L'exemple de référence : A (essai) 2 × 95 + 10 × 11, B (beta) 4 × 25, livraison 20."""
    numero = nouvelle(client)
    a1, a2 = composant(client, PROJET, "Farnell"), composant(client, PROJET, "Farnell")
    b1 = composant(client, "beta", "Farnell")
    ajouter(
        client,
        numero,
        [ligne(PROJET, a1, 2, 95.0), ligne(PROJET, a2, 10, 11.0), ligne("beta", b1, 4, 25.0)],
    )
    frais = client.post(f"{URL}/{numero}/frais", json={"type_frais": "Livraison", "montant_ht": 20})
    assert frais.status_code == 201, frais.text
    return numero


def copie(app: FastAPI, projet: str, numero: str) -> dict:
    conn = db.connect(base(app, projet), creer=False)
    try:
        trouvee = db.fetch_one(conn, "SELECT * FROM v_commande WHERE commune = ?", (numero,))
        if trouvee is None:
            trouvee = db.fetch_one(conn, "SELECT * FROM commande WHERE commune = ?", (numero,))
        return trouvee
    finally:
        conn.close()


def emplacements(app: FastAPI) -> communes_sync.Emplacements:
    conn = _comptes(app)
    try:
        dossier = conn.execute("SELECT * FROM dossier WHERE code = 'epreuve'").fetchone()
        return communes.emplacements(conn, app.state.registre, dict(dossier))
    finally:
        conn.close()


# --- 1. Répartition (calcul pur) ----------------------------------------------------------------


def _l(qte: int, pu: float | None, statut: str = "Commandee") -> dict:
    return {"qte_commandee": qte, "pu_ht_devis": pu, "qte_recue": 0, "statut_ligne": statut}


def test_repartition_exemple_de_reference() -> None:
    lignes = {"a": [_l(2, 95.0), _l(10, 11.0)], "b": [_l(4, 25.0)]}
    frais = [{"type_frais": "Livraison", "montant_ht": 20.0, "commentaire": None}]
    parts = communes_sync.repartir(lignes, frais, 410.0)
    assert parts["a"]["estime_ht"] == pytest.approx(310.0)
    assert parts["b"]["estime_ht"] == pytest.approx(110.0)
    assert parts["a"]["frais"][0]["montant_ht"] == pytest.approx(10.0)
    assert round(parts["a"]["reel_ht"], 2) == 302.62
    assert round(parts["b"]["reel_ht"], 2) == 107.38
    assert communes_sync.repartir(lignes, frais, None)["a"]["reel_ht"] is None


def test_somme_des_parts_egale_au_reel_a_trois_projets() -> None:
    lignes = {"a": [_l(3, 1 / 3)], "b": [_l(7, 0.7)], "c": [_l(1, 10.01), _l(5, None)]}
    frais = [{"type_frais": "Livraison", "montant_ht": 9.99, "commentaire": None}]
    parts = communes_sync.repartir(lignes, frais, 1000 / 7)
    assert abs(sum(p["reel_ht"] for p in parts.values()) - 1000 / 7) < 1e-9
    assert parts["c"]["sans_prix"] == 1
    assert parts["c"]["lignes_ht"] == pytest.approx(10.01)


def test_estime_nul_parts_egales_et_projet_absent_sans_frais() -> None:
    lignes = {"a": [_l(1, None)], "b": [_l(1, None)], "c": [_l(1, 5.0, "Annulee")]}
    frais: list[dict] = []
    parts = communes_sync.repartir(lignes, frais, 90.0)
    assert parts["a"]["reel_ht"] == pytest.approx(45.0)
    assert parts["b"]["reel_ht"] == pytest.approx(45.0)
    assert parts["c"]["reel_ht"] == 0.0
    avec_frais = communes_sync.repartir(lignes, [{"montant_ht": 20.0, "type_frais": "x"}], None)
    assert avec_frais["c"]["frais"] == []
    assert avec_frais["a"]["frais"][0]["montant_ht"] == pytest.approx(10.0)


# --- 2. De bout en bout : les copies portent les parts ------------------------------------------


def test_exemple_de_bout_en_bout(app: FastAPI, client: TestClient, exemple: str) -> None:
    assert exemple == "CC-001"
    reponse = client.patch(
        f"{URL}/{exemple}", json={"statut": "Commande", "montant_commande_ht": 410}
    )
    assert reponse.status_code == 200, reponse.text
    a, b = copie(app, PROJET, exemple), copie(app, "beta", exemple)
    assert a["numero"].startswith("CMD-") and a["statut"] == "Commande" and a["engagee"] == 1
    assert a["montant_frais_ht"] == pytest.approx(10.0)
    assert a["total_ht"] == pytest.approx(310.0)
    assert b["total_ht"] == pytest.approx(110.0)
    assert a["montant_commande_ht"] + b["montant_commande_ht"] == pytest.approx(410.0, abs=1e-9)
    assert round(a["montant_commande_ht"], 2) == 302.62
    assert a["version_commune"] == b["version_commune"]
    statuts = lire(
        app,
        "beta",
        "SELECT statut_ligne FROM ligne_commande WHERE commande_numero = ?",
        (b["numero"],),
    )
    assert statuts == [("Commandee",)]
    lecture = client.get(f"{URL}/{exemple}").json()
    assert lecture["statut_affiche"] == "Commande"
    parts = {p["projet"]: p["part"]["reel_ht"] for p in lecture["projets"]}
    assert parts == {PROJET: 302.62, "beta": 107.38}
    liste = client.get(URL).json()
    assert liste["acheteur"] is True
    assert liste["communes"][0]["estime_ht"] == pytest.approx(420.0)


def test_statut_livre_ne_se_pose_pas_a_la_main(client: TestClient, exemple: str) -> None:
    reponse = client.patch(f"{URL}/{exemple}", json={"statut": "Livre"})
    assert reponse.status_code == 400
    assert "réceptions" in reponse.json()["erreur"]


def test_ligne_annulee_fait_sortir_un_projet_des_frais(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    b = copie(app, "beta", exemple)
    (identifiant,) = lire(
        app, "beta", "SELECT id FROM ligne_commande WHERE commande_numero = ?", (b["numero"],)
    )[0]
    reponse = client.patch(
        f"{URL}/{exemple}/lignes/beta/{identifiant}", json={"statut_ligne": "Annulee"}
    )
    assert reponse.status_code == 200, reponse.text
    assert copie(app, PROJET, exemple)["montant_frais_ht"] == pytest.approx(20.0)
    assert copie(app, "beta", exemple)["montant_frais_ht"] == 0


def test_archiver_la_commune_archive_les_copies(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    assert client.delete(f"{URL}/{exemple}").status_code == 200
    assert copie(app, PROJET, exemple)["archive"] == 1
    assert client.get(URL).json()["communes"] == []


# --- 3. Verrou de la copie, voie par voie (point 4) ---------------------------------------------


VOIES = [
    "UPDATE commande SET statut = 'Refuse' WHERE numero = :n",
    "UPDATE commande SET archive = 1 WHERE numero = :n",
    "UPDATE commande SET montant_commande_ht = 1 WHERE numero = :n",
    "DELETE FROM commande WHERE numero = :n",
    "INSERT INTO ligne_commande (commande_numero, composant_id, qte_commandee)"
    " SELECT :n, id, 1 FROM composant LIMIT 1",
    "UPDATE ligne_commande SET qte_commandee = 99 WHERE commande_numero = :n",
    "UPDATE ligne_commande SET qte_recue = 1 WHERE commande_numero = :n",
    "DELETE FROM ligne_commande WHERE commande_numero = :n",
    "INSERT INTO frais_commande (commande_numero, type_frais, montant_ht)"
    " VALUES (:n, 'Livraison', 1)",
    "UPDATE frais_commande SET montant_ht = 0 WHERE commande_numero = :n",
    "DELETE FROM frais_commande WHERE commande_numero = :n",
    "INSERT INTO document (commande_numero, type_document, nom_origine, chemin, taille, empreinte)"
    " VALUES (:n, 'Devis', 'a.pdf', 'a.pdf', 1, 'x')",
    "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte, commande_numero)"
    " SELECT '2026-10-23', id, 'Entree', 'Reception achat', 1, :n FROM composant LIMIT 1",
]


@pytest.mark.parametrize("requete", VOIES)
def test_copie_verrouillee_en_base(
    app: FastAPI, client: TestClient, exemple: str, requete: str
) -> None:
    numero_local = copie(app, PROJET, exemple)["numero"]
    conn = db.connect(base(app, PROJET), creer=False)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="commande commune"):
            conn.execute(requete, {"n": numero_local})
    finally:
        conn.close()


def test_copie_verrouillee_par_l_api_du_projet(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    numero_local = copie(app, PROJET, exemple)["numero"]
    url = f"/p/{PROJET}/api/commandes/{numero_local}"
    assert client.get(url).status_code == 200
    assert client.patch(url, json={"commentaire": "x"}).status_code == 409
    assert client.delete(url).status_code == 409
    a1 = composant(client, PROJET, "Farnell")
    corps = {"composant_id": a1, "qte_commandee": 1}
    assert client.post(f"{url}/lignes", json=corps).status_code == 409


def test_renommage_du_fournisseur_passe_par_les_copies(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    reponse = client.patch(f"/p/{ORG}/api/fournisseurs/Farnell", json={"nom": "Farnell France"})
    assert reponse.status_code == 200, reponse.text
    assert copie(app, PROJET, exemple)["fournisseur_nom"] == "Farnell France"
    modif = client.patch(f"{URL}/{exemple}", json={"montant_commande_ht": 410})
    assert modif.status_code == 200, modif.text
    assert modif.json()["fournisseur_nom"] == "Farnell France"
    assert modif.json()["synchronisation"]["ecrites"] == ["beta", PROJET]


# --- 4. Version : synchronisations entrelacées, écriture interrompue (point 1) -----------------


def test_synchronisations_entrelacees(
    app: FastAPI, client: TestClient, exemple: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S1 lit l'état ; une écriture (ligne de 50 € dans beta) et sa synchronisation S2 passent
    pendant ce temps ; S1 ne doit rien écrire de périmé. Part de B = recalcul complet."""
    emp = emplacements(app)
    b2 = composant(client, "beta", "Farnell")
    lire_vrai = communes_sync.lignes_du_projet
    deja: list[bool] = []

    def lire_puis_ecrire(chemin: Path, numero_local: str) -> list[dict]:
        lignes = lire_vrai(chemin, numero_local)
        if not deja:
            deja.append(True)
            monkeypatch.setattr(communes_sync, "lignes_du_projet", lire_vrai)
            ajouter(client, exemple, [ligne("beta", b2, 2, 25.0)])
        return lignes

    client.patch(f"{URL}/{exemple}", json={"montant_commande_ht": 410})
    monkeypatch.setattr(communes_sync, "lignes_du_projet", lire_puis_ecrire)
    rapport = communes_sync.synchroniser(emp, exemple)
    assert rapport["perimee"] is True and rapport["ecrites"] == []
    # Recalcul complet : A 310, B 160 (100 + 50 + 10), réel 410.
    b = copie(app, "beta", exemple)
    assert b["total_ht"] == pytest.approx(160.0)
    assert b["montant_commande_ht"] == pytest.approx(410 * 160 / 470)


def test_ecriture_interrompue_rattrapee_a_l_ouverture(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    """Version augmentée et ligne écrite dans beta, puis coupure avant la synchronisation."""
    emp = emplacements(app)
    b2 = composant(client, "beta", "Farnell")
    numero_local = copie(app, "beta", exemple)["numero"]
    ref = db.connect(emp.reference, creer=False)
    try:
        communes_sync.augmenter_version(ref, exemple)
    finally:
        ref.close()
    conn = db.connect(base(app, "beta"), creer=False)
    try:
        with communes_sync.ouverte(conn):
            db.insert_row(
                conn,
                "ligne_commande",
                {
                    "commande_numero": numero_local,
                    "composant_id": b2,
                    "qte_commandee": 2,
                    "pu_ht_devis": 25.0,
                },
            )
    finally:
        conn.close()
    assert communes_sync.en_retard(emp) == [exemple]
    assert copie(app, "beta", exemple)["montant_frais_ht"] == pytest.approx(10.0)
    lecture = client.get(f"{URL}/{exemple}")
    assert lecture.status_code == 200
    assert communes_sync.en_retard(emp) == []
    assert copie(app, "beta", exemple)["total_ht"] == pytest.approx(160.0)


# --- 5. Participant hors ligne, référence restaurée (point 5) -----------------------------------


def test_participant_hors_ligne_rien_n_est_ecrit(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    avant = copie(app, PROJET, exemple)
    beta = app.state.registre.projets.pop("beta")
    try:
        reponse = client.patch(f"{URL}/{exemple}", json={"montant_commande_ht": 410})
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["synchronisation"]["manquants"] == ["beta"]
        assert reponse.json()["manquants"] == ["beta"]
        apres = copie(app, PROJET, exemple)
        assert apres["montant_commande_ht"] == avant["montant_commande_ht"]
        assert apres["version_commune"] == avant["version_commune"]
    finally:
        app.state.registre.projets["beta"] = beta
    client.get(f"{URL}/{exemple}")
    assert round(copie(app, PROJET, exemple)["montant_commande_ht"], 2) == 302.62


def test_reference_restauree_numero_non_reattribue(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    emp = emplacements(app)
    ref = db.connect(emp.reference, creer=False)
    try:
        with db.transaction(ref):
            ref.execute("DELETE FROM frais_commune")
            ref.execute("DELETE FROM commune_projet")
            ref.execute("DELETE FROM commune")
    finally:
        ref.close()
    assert nouvelle(client) == "CC-002"


# --- 6. Droits ----------------------------------------------------------------------------------


def test_droits(app: FastAPI, client: TestClient, exemple: str) -> None:
    membre_organisme(app, "lecture@ecole.test", "meca", "lecture")
    lecture = connecter(app, "lecture@ecole.test")
    assert lecture.get(f"{URL}/{exemple}").status_code == 200
    assert lecture.get(URL).json()["acheteur"] is False
    assert lecture.post(URL, json={"fournisseur_nom": "Farnell"}).status_code == 403
    assert lecture.patch(f"{URL}/{exemple}", json={"commentaire": "x"}).status_code == 403

    membre_organisme(app, "achats@ecole.test", "meca", "achats_stock")
    achats = connecter(app, "achats@ecole.test")
    assert achats.patch(f"{URL}/{exemple}", json={"commentaire": "x"}).status_code == 200

    # Membre d'un projet avec la permission achats : lit sa copie, pas la commune.
    identifiant = creer_compte(app, "equipe@ecole.test", "contributeur", permissions=("achats",))
    equipe = connecter(app, "equipe@ecole.test")
    assert equipe.get(URL).status_code == 403
    numero_local = copie(app, PROJET, exemple)["numero"]
    assert equipe.get(f"/p/{PROJET}/api/commandes/{numero_local}").status_code == 200

    # Devenu responsable achats du dossier, il gère les communes.
    conn = _comptes(app)
    try:
        from backend.services import hierarchie
        from tests.test_hierarchie import SERVEUR

        hierarchie.add_responsable(conn, SERVEUR, "epreuve", identifiant)
    finally:
        conn.close()
    assert equipe.patch(f"{URL}/{exemple}", json={"commentaire": "y"}).status_code == 200


def test_fournisseur_hors_liste_refuse(client: TestClient) -> None:
    reponse = client.post(URL, json={"fournisseur_nom": "Inconnu"})
    assert reponse.status_code == 400


# --- 7. Projet qui quitte le dossier (point 7) --------------------------------------------------


def test_sortie_refusee_tant_qu_il_a_des_lignes(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    from backend.erreurs import Conflit

    with pytest.raises(Conflit, match="CC-001"):
        ranger(app, "beta", {"dossier": None})
    b = copie(app, "beta", exemple)
    (identifiant,) = lire(
        app, "beta", "SELECT id FROM ligne_commande WHERE commande_numero = ?", (b["numero"],)
    )[0]
    client.patch(f"{URL}/{exemple}/lignes/beta/{identifiant}", json={"statut_ligne": "Annulee"})
    ranger(app, "beta", {"dossier": None})


# --- 8. Numéro de la copie : jamais une commande ordinaire, copie orpheline reprise -------------


def test_numero_pris_par_une_commande_ordinaire_refuse(
    app: FastAPI, client: TestClient, exemple: str
) -> None:
    """Inscription qui pointe vers une commande ordinaire (référence restaurée, par exemple) :
    les lignes de la commune n'y entrent pas."""
    ordinaire = client.post(f"/p/{PROJET}/api/commandes", json={"fournisseur_nom": "Farnell"})
    assert ordinaire.status_code == 201, ordinaire.text
    numero_ordinaire = ordinaire.json()["numero"]
    emp = emplacements(app)
    ref = db.connect(emp.reference, creer=False)
    try:
        with db.transaction(ref):
            ref.execute(
                "UPDATE commune_projet SET numero_local = ? WHERE projet = ?",
                (numero_ordinaire, PROJET),
            )
    finally:
        ref.close()
    a3 = composant(client, PROJET, "Farnell")
    reponse = client.post(f"{URL}/{exemple}/lignes", json={"lignes": [ligne(PROJET, a3, 1, 5.0)]})
    assert reponse.status_code == 409
    assert lire(
        app,
        PROJET,
        "SELECT COUNT(*) FROM ligne_commande WHERE commande_numero = ?",
        (numero_ordinaire,),
    ) == [(0,)]


def test_copie_orpheline_reprise(app: FastAPI, client: TestClient) -> None:
    """Copie créée dans le projet, inscription dans la référence interrompue : la ligne
    suivante reprend cette copie, sans en créer une seconde."""
    numero = nouvelle(client)
    emp = emplacements(app)
    ref = db.connect(emp.reference, creer=False)
    try:
        commune = communes_sync.lire_commune(ref, numero)
    finally:
        ref.close()
    orpheline = communes_sync.creer_copie(base(app, "beta"), None, commune)
    b1 = composant(client, "beta", "Farnell")
    ajouter(client, numero, [ligne("beta", b1, 3, 2.0)])
    copies = lire(app, "beta", "SELECT numero FROM commande WHERE commune = ?", (numero,))
    assert copies == [(orpheline,)]
    assert client.get(f"{URL}/{numero}").json()["projets"][0]["numero_local"] == orpheline
