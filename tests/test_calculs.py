"""Calculs des vues SQL, sur base temporaire vide ou remplie par le jeu d'essai."""

import sqlite3

import pytest

from backend import db
from tests import jeu_essai


def _composant(conn: sqlite3.Connection, **champs: object) -> str:
    """Insère un composant de test dans un bloc de test, avec des valeurs par défaut."""
    conn.execute("INSERT OR IGNORE INTO bloc (code, nom, ordre) VALUES ('TST', 'Test', 1)")
    valeurs = {
        "id": "T-TST-001",
        "bloc_code": "TST",
        "fonction": "Fonction de test",
        "designation": "Composant de test",
        "mode_appro": "Achat",
        "qte_besoin": 1,
    } | champs
    colonnes = ", ".join(valeurs)
    marques = ", ".join("?" for _ in valeurs)
    conn.execute(
        f"INSERT INTO composant ({colonnes}) VALUES ({marques})",  # noqa: S608
        tuple(valeurs.values()),
    )
    return str(valeurs["id"])


def _ensemble(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("INSERT INTO ensemble (code, nom) VALUES (?, ?)", (code, f"Ensemble {code}"))


def _vue(conn: sqlite3.Connection, identifiant: str) -> dict:
    ligne = db.fetch_one(conn, "SELECT * FROM v_composant WHERE id = ?", (identifiant,))
    assert ligne is not None
    return ligne


# --- Calculs unitaires -------------------------------------------------------------


def test_prix_ttc_converti_en_ht(conn_vide: sqlite3.Connection) -> None:
    _composant(conn_vide, pu_releve=204, base_prix_releve="TTC", taux_tva=0.2)
    assert _vue(conn_vide, "T-TST-001")["pu_ht"] == pytest.approx(170.00, abs=0.001)


def test_mode_hors_achat_ne_coute_rien(conn_vide: sqlite3.Connection) -> None:
    conn_vide.execute(
        "INSERT INTO valeur_liste (liste, code, libelle) VALUES ('mode_appro', 'Fourni', 'Fourni')"
    )
    _composant(conn_vide, mode_appro="Fourni", pu_releve=50, qte_besoin=2)
    assert _vue(conn_vide, "T-TST-001")["total_ht"] == 0


def test_achat_sans_prix_est_a_chiffrer(conn_vide: sqlite3.Connection) -> None:
    _composant(conn_vide, pu_releve=None)
    assert _vue(conn_vide, "T-TST-001")["a_chiffrer"] == 1


def test_qte_a_acheter_jamais_negative(conn_vide: sqlite3.Connection) -> None:
    _composant(conn_vide, qte_besoin=1, qte_rechange=0, qte_disponible=5, pu_releve=10)
    vue = _vue(conn_vide, "T-TST-001")
    assert vue["qte_a_acheter"] == 0
    assert vue["total_ht"] == 0


def test_composant_non_affecte_n_est_pas_un_ecart(conn_vide: sqlite3.Connection) -> None:
    _composant(conn_vide, qte_besoin=3)
    assert _vue(conn_vide, "T-TST-001")["qte_affectee"] == 0
    pilotage = db.fetch_one(conn_vide, "SELECT * FROM v_pilotage")
    assert pilotage is not None
    assert pilotage["nb_composants_ecart_affectation"] == 0
    assert pilotage["nb_composants_non_affectes"] == 1


def test_ecart_affectation(conn_vide: sqlite3.Connection) -> None:
    identifiant = _composant(conn_vide, qte_besoin=3)
    for code in ("NAC", "MAT"):
        _ensemble(conn_vide, code)
        conn_vide.execute(
            "INSERT INTO affectation (ensemble_code, composant_id, qte) VALUES (?, ?, 1)",
            (code, identifiant),
        )
    vue = _vue(conn_vide, identifiant)
    assert vue["qte_affectee"] == 2
    assert vue["nb_ensembles"] == 2
    assert vue["ecart_affectation"] == 1
    pilotage = db.fetch_one(conn_vide, "SELECT * FROM v_pilotage")
    assert pilotage is not None
    assert pilotage["nb_composants_ecart_affectation"] == 1


def test_montage_compte_sortie_positive_et_retour_negatif(conn_vide: sqlite3.Connection) -> None:
    identifiant = _composant(conn_vide, qte_besoin=2)
    _ensemble(conn_vide, "NAC")
    conn_vide.execute(
        "INSERT INTO affectation (ensemble_code, composant_id, qte) VALUES ('NAC', ?, 2)",
        (identifiant,),
    )
    mouvements = [
        ("Entree", "Inventaire", 2, None),
        ("Sortie", "Sortie montage", 2, "NAC"),
        ("Entree", "Retour montage", 1, "NAC"),
    ]
    for sens, type_mouvement, qte, ensemble in mouvements:
        conn_vide.execute(
            "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte,"
            " ensemble_code) VALUES ('2026-10-01', ?, ?, ?, ?, ?)",
            (identifiant, sens, type_mouvement, qte, ensemble),
        )
    ligne = db.fetch_one(
        conn_vide, "SELECT * FROM v_ensemble_composant WHERE composant_id = ?", (identifiant,)
    )
    assert ligne is not None
    assert ligne["qte_montee"] == 1
    assert ligne["reste_a_monter"] == 1
    assert _vue(conn_vide, identifiant)["stock_actuel"] == 1
    ensemble = db.fetch_one(conn_vide, "SELECT * FROM v_ensemble WHERE code = 'NAC'")
    assert ensemble is not None
    assert ensemble["avancement_montage_pct"] == pytest.approx(50.0)


def test_mouvement_de_montage_exige_un_ensemble(conn_vide: sqlite3.Connection) -> None:
    identifiant = _composant(conn_vide)
    with pytest.raises(sqlite3.IntegrityError):
        conn_vide.execute(
            "INSERT INTO mouvement_stock (date, composant_id, sens, type_mouvement, qte)"
            " VALUES ('2026-10-01', ?, 'Sortie', 'Sortie montage', 1)",
            (identifiant,),
        )


def test_bloc_sans_budget_a_un_ecart_nul(conn_vide: sqlite3.Connection) -> None:
    _composant(conn_vide, pu_releve=10)
    bloc = db.fetch_one(conn_vide, "SELECT * FROM v_bloc WHERE code = 'TST'")
    assert bloc is not None
    assert bloc["cout_ht"] == pytest.approx(10.0)
    assert bloc["ecart_budget"] is None


def test_devis_n_engage_rien(conn_vide: sqlite3.Connection) -> None:
    identifiant = _composant(conn_vide, pu_releve=10, qte_besoin=2)
    conn_vide.execute(
        "INSERT INTO commande (numero, type, statut, port_ht) VALUES"
        " ('CMD-001', 'Devis', 'Devis recu', 5), ('CMD-002', 'Commande', 'Commande', 7)"
    )
    for numero in ("CMD-001", "CMD-002"):
        conn_vide.execute(
            "INSERT INTO ligne_commande (commande_numero, composant_id, qte_commandee,"
            " pu_ht_devis, statut_ligne) VALUES (?, ?, 2, 10, 'Commandee')",
            (numero, identifiant),
        )
    pilotage = db.fetch_one(conn_vide, "SELECT * FROM v_pilotage")
    assert pilotage is not None
    assert pilotage["montant_engage_ht"] == pytest.approx(27.0)
    bloc = db.fetch_one(conn_vide, "SELECT * FROM v_bloc WHERE code = 'TST'")
    assert bloc is not None
    assert bloc["montant_engage_ht"] == pytest.approx(20.0)
    assert _vue(conn_vide, identifiant)["avancement"] == "Commande"


# --- Jeu d'essai ---------------------------------------------------------------------


def _compte(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


def test_jeu_essai_volumes(conn_essai: sqlite3.Connection) -> None:
    attendus = {
        "composant": 60,
        "bloc": 9,
        "fournisseur": 16,
        "ensemble": 0,
        "affectation": 0,
        "commande": 0,
        "ligne_commande": 0,
        "mouvement_stock": 0,
    }
    assert {table: _compte(conn_essai, table) for table in attendus} == attendus
    nb_ali = conn_essai.execute("SELECT COUNT(*) FROM composant WHERE bloc_code = 'ALI'")
    assert nb_ali.fetchone()[0] == 20
    parametres = dict(conn_essai.execute("SELECT cle, valeur FROM parametre").fetchall())
    assert parametres == jeu_essai.PARAMETRES


def test_pu_ht_non_arrondi_dans_la_vue(conn_essai: sqlite3.Connection) -> None:
    assert _vue(conn_essai, "ESSAI-ODB-005")["pu_ht"] == pytest.approx(11.95 / 1.2, abs=1e-9)


def test_total_ht_du_jeu_essai(conn_essai: sqlite3.Connection) -> None:
    ligne = conn_essai.execute(
        "SELECT TOTAL(total_ht), COUNT(CASE WHEN mode_appro = 'Achat'"
        " AND pu_releve IS NOT NULL THEN 1 END) FROM v_composant"
    ).fetchone()
    assert ligne[0] == pytest.approx(3184.98, abs=0.01)
    assert ligne[1] == 44


def test_pilotage_du_jeu_essai(conn_essai: sqlite3.Connection) -> None:
    pilotage = db.fetch_one(conn_essai, "SELECT * FROM v_pilotage")
    assert pilotage is not None
    assert pilotage["nb_composants"] == 60
    assert pilotage["nb_a_chiffrer"] == 11
    assert pilotage["cout_ht"] == pytest.approx(3184.98, abs=0.01)
    assert pilotage["ecart_budget_ht"] == pytest.approx(184.98, abs=0.01)
    assert pilotage["budget_ht"] == pytest.approx(3000)
    assert pilotage["nb_ensembles"] == 0
    assert pilotage["montant_engage_ht"] == 0
    assert pilotage["reste_a_engager_ht"] == pytest.approx(3000)
