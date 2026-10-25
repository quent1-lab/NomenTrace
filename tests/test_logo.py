"""Logo de l'établissement : envoi, contrôle de l'image, reprise dans les demandes de devis."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import GifImagePlugin, Image, TiffImagePlugin

from tests.test_demande_document import _demande


def _image(format_image: str = "PNG", taille: tuple[int, int] = (200, 80)) -> bytes:
    flux = io.BytesIO()
    Image.new("RGB", taille, (30, 90, 160)).save(flux, format=format_image)
    return flux.getvalue()


def _envoyer(client: TestClient, contenu: bytes, nom: str = "logo.png"):
    return client.post("/api/parametres/logo", files={"fichier": (nom, contenu)})


def test_envoi_lecture_et_retrait(client_essai: TestClient) -> None:
    assert client_essai.get("/api/parametres/logo/infos").json() == {"present": False}
    assert client_essai.get("/api/parametres/logo").status_code == 404
    reponse = _envoyer(client_essai, _image())
    assert reponse.status_code == 200, reponse.text
    assert reponse.json() == {"type_mime": "image/png", "largeur": 200, "hauteur": 80}
    image = client_essai.get("/api/parametres/logo")
    assert image.headers["content-type"] == "image/png"
    assert image.content == _image()
    # Un nouvel envoi remplace le précédent.
    assert _envoyer(client_essai, _image("JPEG", (90, 90)), "logo.jpg").status_code == 200
    infos = client_essai.get("/api/parametres/logo/infos").json()
    assert (infos["present"], infos["largeur"]) == (True, 90)
    journal = client_essai.get("/api/journal", params={"table_cible": "parametre"}).json()
    assert any(j["cle_cible"] == "logo" for j in journal)
    assert client_essai.delete("/api/parametres/logo").status_code == 200
    assert client_essai.get("/api/parametres/logo/infos").json() == {"present": False}
    assert client_essai.delete("/api/parametres/logo").status_code == 404


def test_fichier_refuse(client_essai: TestClient) -> None:
    for contenu in (b"", b"pas une image", _image("GIF")):
        reponse = _envoyer(client_essai, contenu)
        assert reponse.status_code == 400, contenu[:10]
        assert "erreur" in reponse.json()
    assert _envoyer(client_essai, _image(taille=(4001, 10))).status_code == 400


def test_seuls_png_et_jpeg_sont_decodes(
    client_essai: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un logo ne passe que par les décodeurs PNG et JPEG : les failles des autres formats
    de Pillow (TIFF, GIF, FPX, EPS…) ne sont pas atteignables par un envoi."""
    ouverts = []
    for classe in (TiffImagePlugin.TiffImageFile, GifImagePlugin.GifImageFile):
        origine = classe._open

        def espion(self: object, origine: object = origine) -> None:
            ouverts.append(type(self).__name__)
            origine(self)

        monkeypatch.setattr(classe, "_open", espion)
    for format_image in ("TIFF", "GIF"):
        assert _envoyer(client_essai, _image(format_image)).status_code == 400
    assert ouverts == []


def test_logo_dans_les_demandes_de_devis(client_essai: TestClient) -> None:
    numero = _demande(client_essai)
    sans = client_essai.get(f"/api/commandes/{numero}/demande-devis.pdf").content
    _envoyer(client_essai, _image())
    pdf = client_essai.get(f"/api/commandes/{numero}/demande-devis.pdf").content
    assert b"/Subtype /Image" in pdf and b"/Subtype /Image" not in sans
    excel = client_essai.get(f"/api/commandes/{numero}/demande-devis.xlsx").content
    with zipfile.ZipFile(io.BytesIO(excel)) as archive:
        assert any(nom.startswith("xl/media/") for nom in archive.namelist())
