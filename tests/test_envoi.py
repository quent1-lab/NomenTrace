"""Limites d'envoi de fichiers : plafond du serveur, refusé avant réception, et taille
maximale d'un document réglée par projet sous ce plafond."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.conftest import client_local

MO = 1024 * 1024
COMPOSANT = "/api/composants/ESSAI-TR-001/documents"


def _pdf(taille: int) -> bytes:
    entete = b"%PDF-1.4\n"
    return entete + b"0" * (taille - len(entete))


def _deposer(client: TestClient, contenu: bytes, nom: str = "fiche.pdf"):
    return client.post(
        COMPOSANT,
        files=[("fichiers", (nom, contenu))],
        data={"type_document": "Fiche technique"},
    )


@pytest.fixture
def client_plafond(
    conn_essai: object, dossier_data: Path, dossier_echange: Path
) -> Iterator[TestClient]:
    """Jeu d'essai servi avec un plafond d'envoi de 1 Mo."""
    conn_essai.close()  # type: ignore[attr-defined]
    app = create_app(
        dossier_data, dossier_echange=dossier_echange, mode_local=True, envoi_max_octets=MO
    )
    with client_local(app) as test_client:
        yield test_client


def test_envoi_au_dela_du_plafond_refuse_avant_lecture(client_plafond: TestClient) -> None:
    reponse = _deposer(client_plafond, _pdf(MO + 200 * 1024))
    assert reponse.status_code == 413
    assert reponse.json()["erreur"] == "Envoi trop volumineux : 1 Mo au plus à la fois."
    assert client_plafond.get(COMPOSANT).json() == []


def test_envoi_sans_longueur_annoncee_coupe_au_plafond(client_plafond: TestClient) -> None:
    """Un corps envoyé par morceaux, sans Content-Length, est compté pendant la lecture."""

    limite = b"limite-essai"
    entete = (
        b"--" + limite + b'\r\nContent-Disposition: form-data; name="type_document"\r\n\r\n'
        b"Plan\r\n--" + limite + b'\r\nContent-Disposition: form-data; name="fichiers";'
        b' filename="plan.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.4\n'
    )

    def morceaux() -> Iterator[bytes]:
        yield entete
        for _ in range(20):
            yield b"0" * (100 * 1024)
        yield b"\r\n--" + limite + b"--\r\n"

    reponse = client_plafond.post(
        COMPOSANT,
        content=morceaux(),
        headers={"Content-Type": f"multipart/form-data; boundary={limite.decode()}"},
    )
    assert reponse.status_code == 413
    assert "1 Mo au plus" in reponse.json()["erreur"]


def test_envoi_sous_le_plafond_accepte(client_plafond: TestClient) -> None:
    assert _deposer(client_plafond, _pdf(500 * 1024)).status_code == 201


def test_limites_publiees_avec_leurs_valeurs_par_defaut(client_essai: TestClient) -> None:
    limites = client_essai.get("/api/envoi").json()
    assert limites["envoi_max_octets"] == 100 * MO
    assert limites["document_max_octets"] == 20 * MO
    assert ".pdf" in limites["extensions"]
    assert ".exe" not in limites["extensions"]


def test_taille_d_un_document_reglee_par_le_projet(client_essai: TestClient) -> None:
    reponse = client_essai.patch("/api/parametres", json={"taille_max_document_mo": 1})
    assert reponse.status_code == 200
    assert client_essai.get("/api/envoi").json()["document_max_octets"] == MO
    refus = _deposer(client_essai, _pdf(MO + 1))
    assert refus.status_code == 400
    assert refus.json()["erreur"] == "Le fichier « fiche.pdf » dépasse 1 Mo."
    assert _deposer(client_essai, _pdf(MO)).status_code == 201


def test_gros_document_accepte_si_le_projet_le_permet(client_essai: TestClient) -> None:
    client_essai.patch("/api/parametres", json={"taille_max_document_mo": 30})
    assert _deposer(client_essai, _pdf(25 * MO)).status_code == 201


@pytest.mark.parametrize(("valeur", "statut"), [(0, 422), (101, 400), (2.5, 422)])
def test_taille_d_un_document_bornee(client_essai: TestClient, valeur: float, statut: int) -> None:
    reponse = client_essai.patch("/api/parametres", json={"taille_max_document_mo": valeur})
    assert reponse.status_code == statut
    assert client_essai.get("/api/envoi").json()["document_max_octets"] == 20 * MO


def test_plafond_du_serveur_lu_dans_l_environnement() -> None:
    from backend import config

    assert config.lire_envoi_max(None) == 100
    assert config.lire_envoi_max("250") == 250
    with pytest.raises(ValueError, match="NOMENTRACE_ENVOI_MAX_MO"):
        config.lire_envoi_max("0")
