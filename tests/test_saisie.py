"""Contrôle de la forme des champs texte : refus des erreurs évidentes, signalement du reste."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.services import saisie
from tests.test_import import _appliquer, _decisions_par_defaut, _deposer, _modele, _modifier

ACHAT = {
    "bloc_code": "ALI",
    "fonction": "Essai",
    "designation": "Composant d'essai",
    "mode_appro": "Achat",
    "qte_besoin": 1,
}
COMPOSANT = "ESSAI-OBS-002"


@pytest.mark.parametrize(
    "reference",
    [
        "https://www.exemple.test/produit/123",
        "www.exemple.test/123",
        "exemple.com/produit/123",
        "LM317T\nTO-220",
    ],
)
def test_reference_evidemment_fausse_refusee(client_essai: TestClient, reference: str) -> None:
    refus = client_essai.post("/api/composants", json={**ACHAT, "ref_fabricant": reference})
    assert refus.status_code == 400
    assert "Réf fabricant" in refus.json()["erreur"]
    modif = client_essai.patch(f"/api/composants/{COMPOSANT}", json={"ref_fabricant": reference})
    assert modif.status_code == 400


@pytest.mark.parametrize("reference", ["LM317T", "RC0805FR-0710KL", "BC547B/TO92", "M3x12 DIN912"])
def test_references_ordinaires_acceptees(client_essai: TestClient, reference: str) -> None:
    cree = client_essai.post("/api/composants", json={**ACHAT, "ref_fabricant": reference})
    assert cree.status_code == 201, cree.text
    assert saisie.a_verifier({"ref_fabricant": reference}) == []


def test_lien_dans_la_designation_refuse(client_essai: TestClient) -> None:
    refus = client_essai.post(
        "/api/composants", json={**ACHAT, "designation": "voir https://exemple.test/x"}
    )
    assert refus.status_code == 400
    assert "Désignation" in refus.json()["erreur"]


def test_existant_mal_rempli_reste_modifiable_et_signale(
    client_essai: TestClient, chemin_base: Path
) -> None:
    """Une erreur déjà en base ne bloque que la saisie de ce champ ; Nettoyage la signale."""
    # Écriture directe en base, comme une donnée antérieure à la règle.
    conn = db.connect(chemin_base)
    conn.execute(
        "UPDATE composant SET ref_fabricant = ? WHERE id = ?",
        ("https://exemple.test/produit", COMPOSANT),
    )
    conn.commit()
    conn.close()
    assert (
        client_essai.patch(f"/api/composants/{COMPOSANT}", json={"pu_releve": 12}).status_code
        == 200
    )
    controles = client_essai.get("/api/nettoyage/composants").json()
    ligne = next(c for c in controles["composants"] if c["id"] == COMPOSANT)
    assert "saisie_a_verifier" in ligne["controles"]
    assert "adresse web" in ligne["a_verifier"][0]


def test_reference_inhabituelle_signalee_sans_refus(client_essai: TestClient) -> None:
    longue = "Moteur pas à pas NEMA 17 avec réducteur planétaire"
    cree = client_essai.post("/api/composants", json={**ACHAT, "ref_fabricant": longue})
    assert cree.status_code == 201
    controles = client_essai.get("/api/nettoyage/composants").json()
    ligne = next(c for c in controles["composants"] if c["id"] == cree.json()["id"])
    assert ligne["a_verifier"] == ["Réf fabricant de plus de 40 caractères"]
    assert saisie.a_verifier({"ref_fabricant": "Vis tête fraisée inox"}) == [
        "Réf fabricant qui ressemble à une description"
    ]


def test_import_refuse_la_ligne(client_essai: TestClient) -> None:
    contenu = _modifier(
        _modele(client_essai, "/api/blocs/OBS/modele"),
        COMPOSANT,
        "Réf fabricant",
        "https://exemple.test/produit",
    )
    depot = _deposer(client_essai, [("obs.xlsx", contenu)])
    resultat = _appliquer(client_essai, depot, _decisions_par_defaut(depot))
    assert resultat["appliquees"] == 0
    assert "adresse web" in resultat["refus"][0]
