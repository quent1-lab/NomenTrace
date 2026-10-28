"""Préparation des demandes de devis : ce qu'il reste à commander, regroupé par fournisseur.

Un composant est proposé s'il est en mode Achat et qu'il reste des pièces à commander
(reste_a_commander de v_composant). La demande créée est une commande de type Devis, au
statut « A demander », une par fournisseur ; chaque ligne porte le reste à commander. Le
PU HT du devis reste vide : il viendra du devis reçu.
"""

import sqlite3

from backend import db
from backend.erreurs import ErreurMetier
from backend.services import commandes, journal, parametres

# Statuts d'une demande encore ouverte, avant engagement.
STATUTS_DEMANDE_OUVERTE: tuple[str, ...] = (
    "A demander",
    "Devis demande",
    "Devis recu",
    "Devis valide",
)

SQL_CANDIDATS = """
SELECT v.id, v.designation, v.bloc_code, v.fournisseur_nom, v.reste_a_commander, v.pu_ht,
       v.criticite,
       (SELECT group_concat(DISTINCT c.numero)
          FROM ligne_commande l JOIN commande c ON c.numero = l.commande_numero
         WHERE l.composant_id = v.id AND l.statut_ligne <> 'Annulee' AND c.archive = 0
           AND c.statut IN (?, ?, ?, ?)) AS demandes_ouvertes
FROM v_composant v
WHERE v.mode_appro = 'Achat' AND v.reste_a_commander > 0
ORDER BY v.fournisseur_nom IS NULL, v.fournisseur_nom, v.id
"""


SQL_CANDIDATS_COMMANDE = """
SELECT v.id, v.designation, v.reste_a_commander, v.pu_ht,
       (SELECT group_concat(DISTINCT c.numero)
          FROM ligne_commande l JOIN commande c ON c.numero = l.commande_numero
         WHERE l.composant_id = v.id AND l.statut_ligne <> 'Annulee' AND c.archive = 0
           AND c.numero <> :numero
           AND c.statut IN (:s1, :s2, :s3, :s4)) AS demandes_ouvertes
FROM v_composant v
WHERE v.mode_appro = 'Achat' AND v.reste_a_commander > 0 AND v.fournisseur_nom = :fournisseur
  AND NOT EXISTS (SELECT 1 FROM ligne_commande l
                   WHERE l.commande_numero = :numero AND l.composant_id = v.id
                     AND l.statut_ligne <> 'Annulee')
ORDER BY v.id
"""


def list_candidats_commande(conn: sqlite3.Connection, numero: str) -> list[dict]:
    """Composants du fournisseur de la commande qui restent à commander et n'y sont pas,
    par exemple ajoutés au projet après la demande de devis. `demandes_ouvertes` cite les
    autres devis en cours qui les portent déjà : l'écran ne les coche pas d'office."""
    commande = commandes.get_commande(conn, numero)
    parametres_sql = {
        "numero": numero,
        "fournisseur": commande["fournisseur_nom"],
        **{f"s{i}": statut for i, statut in enumerate(STATUTS_DEMANDE_OUVERTE, start=1)},
    }
    candidats = db.fetch_all(conn, SQL_CANDIDATS_COMMANDE, parametres_sql)
    for candidat in candidats:
        ouvertes = candidat["demandes_ouvertes"]
        candidat["demandes_ouvertes"] = ouvertes.split(",") if ouvertes else []
    return candidats


def list_candidats(conn: sqlite3.Connection) -> dict:
    """Composants à commander regroupés par fournisseur, et ceux qui n'en ont pas.

    `demandes_ouvertes` cite les devis déjà en cours pour le composant : l'interface ne le
    coche pas d'office, pour ne pas le demander deux fois.
    """
    groupes: dict[str, list[dict]] = {}
    sans_fournisseur: list[dict] = []
    for ligne in db.fetch_all(conn, SQL_CANDIDATS, STATUTS_DEMANDE_OUVERTE):
        ligne["demandes_ouvertes"] = (
            ligne["demandes_ouvertes"].split(",") if ligne["demandes_ouvertes"] else []
        )
        if ligne["fournisseur_nom"] is None:
            sans_fournisseur.append(ligne)
        else:
            groupes.setdefault(ligne["fournisseur_nom"], []).append(ligne)
    return {
        "fournisseurs": [
            {"fournisseur_nom": nom, "lignes": lignes} for nom, lignes in groupes.items()
        ],
        "sans_fournisseur": sans_fournisseur,
    }


def _choisis(conn: sqlite3.Connection, identifiants: list[str]) -> dict[str, list[dict]]:
    """Composants demandés, relus en base et regroupés par fournisseur."""
    candidats = {c["id"]: c for c in db.fetch_all(conn, SQL_CANDIDATS, STATUTS_DEMANDE_OUVERTE)}
    groupes: dict[str, list[dict]] = {}
    for identifiant in dict.fromkeys(identifiants):
        candidat = candidats.get(identifiant)
        if candidat is None:
            raise ErreurMetier(
                f"{identifiant} n'a plus rien à commander (ou n'est pas en mode Achat)."
            )
        if candidat["fournisseur_nom"] is None:
            raise ErreurMetier(f"{identifiant} n'a pas de fournisseur : renseignez-le d'abord.")
        groupes.setdefault(candidat["fournisseur_nom"], []).append(candidat)
    return groupes


def create_demandes(
    conn: sqlite3.Connection, identifiants: list[str], demande_par: str | None = None
) -> list[dict]:
    """Crée une demande de devis par fournisseur ; renvoie les commandes créées.

    `demande_par` : qui prépare les demandes (l'utilisateur connecté), reporté sur chacune.
    """
    if not identifiants:
        raise ErreurMetier("Aucun composant choisi.")
    numeros: list[str] = []
    with db.transaction(conn):
        taux_tva = parametres.get_taux_tva_defaut(conn)
        for fournisseur, lignes in _choisis(conn, identifiants).items():
            numero = commandes.next_numero(conn)
            db.insert_row(
                conn,
                "commande",
                {
                    "numero": numero,
                    "type": "Devis",
                    "statut": "A demander",
                    "fournisseur_nom": fournisseur,
                    "taux_tva": taux_tva,
                    "demande_par": demande_par,
                },
            )
            journal.write_journal(conn, "commande", numero, "creation", None, "créée")
            for ligne in lignes:
                identifiant = db.insert_row(
                    conn,
                    "ligne_commande",
                    {
                        "commande_numero": numero,
                        "composant_id": ligne["id"],
                        "qte_commandee": ligne["reste_a_commander"],
                    },
                )
                journal.write_journal(
                    conn, "commande", numero, f"ligne {identifiant}", None, ligne["id"]
                )
            numeros.append(numero)
    return [commandes.get_commande(conn, numero) for numero in numeros]
