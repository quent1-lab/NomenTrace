"""Attributs paramétrables des composants : définition, valeurs possibles, valeurs saisies.

Un attribut (la tension, un matériau…) est une donnée créée dans Paramètres, jamais écrit
dans le code. Son code, dérivé du libellé à la création, et son type sont figés ; le
libellé, l'unité, l'ordre et l'état actif se modifient. Une seule valeur par composant et
par attribut, dans valeur_nombre pour le type nombre, dans valeur_texte sinon.
"""

import re
import sqlite3
import unicodedata
from typing import Any

from backend import db
from backend.erreurs import Conflit, ErreurMetier, Introuvable
from backend.services import journal, listes

TYPES: dict[str, str] = {
    "texte": "Texte",
    "nombre": "Nombre",
    "liste": "Liste de valeurs",
    "booleen": "Oui / non",
}
VRAI: frozenset[str] = frozenset({"1", "oui", "o", "vrai", "true", "x", "yes"})
FAUX: frozenset[str] = frozenset({"0", "non", "n", "faux", "false", "no"})
CHAMPS_ATTRIBUT: frozenset[str] = frozenset({"libelle", "unite", "ordre", "actif"})
CHAMPS_VALEUR: tuple[str, ...] = ("libelle", "ordre", "actif")
PREFIXE_CHAMP: str = "attr:"


def code_depuis_libelle(libelle: str) -> str:
    """Code figé d'un attribut : minuscules sans accents, mots reliés par « _ »."""
    decompose = unicodedata.normalize("NFKD", libelle.strip().lower())
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sans_accents).strip("_")


def champ(code: str) -> str:
    """Nom du champ d'un attribut dans les colonnes d'import et d'export : « attr:code »."""
    return f"{PREFIXE_CHAMP}{code}"


def entete(attribut: dict) -> str:
    """En-tête de colonne : le libellé, suivi de l'unité entre parenthèses."""
    return (
        f"{attribut['libelle']} ({attribut['unite']})" if attribut["unite"] else attribut["libelle"]
    )


# --- Définitions ------------------------------------------------------------------------------


def list_attributs(conn: sqlite3.Connection, actifs_seulement: bool = False) -> list[dict]:
    """Attributs triés par ordre, chacun avec ses valeurs possibles (type liste)."""
    attributs = db.fetch_all(
        conn,
        "SELECT * FROM attribut WHERE ? = 0 OR actif = 1 ORDER BY ordre, libelle",
        (int(actifs_seulement),),
    )
    valeurs = db.fetch_all(conn, "SELECT * FROM attribut_valeur ORDER BY ordre, libelle")
    for attribut in attributs:
        attribut["valeurs"] = [v for v in valeurs if v["attribut_code"] == attribut["code"]]
    return attributs


def get_attribut(conn: sqlite3.Connection, code: str) -> dict:
    attribut = db.fetch_one(conn, "SELECT * FROM attribut WHERE code = ?", (code,))
    if attribut is None:
        raise Introuvable(f"Attribut « {code} » inconnu.")
    attribut["valeurs"] = db.fetch_all(
        conn,
        "SELECT * FROM attribut_valeur WHERE attribut_code = ? ORDER BY ordre, libelle",
        (code,),
    )
    return attribut


def check_attribut(conn: sqlite3.Connection, code: str) -> dict:
    """Attribut désigné dans un filtre, un tri ou un export : inconnu = requête refusée (400)."""
    attribut = db.fetch_one(conn, "SELECT * FROM attribut WHERE code = ?", (code,))
    if attribut is None:
        raise ErreurMetier(f"Attribut « {code} » inconnu.")
    return attribut


def create_attribut(conn: sqlite3.Connection, valeurs: dict[str, Any]) -> dict:
    """Crée un attribut en fin de liste ; son code est dérivé du libellé."""
    code = code_depuis_libelle(valeurs["libelle"])
    if not code:
        raise ErreurMetier("Le libellé doit contenir au moins une lettre ou un chiffre.")
    if valeurs["type"] not in TYPES:
        raise ErreurMetier(f"Type d'attribut inconnu : « {valeurs['type']} ».")
    with db.transaction(conn):
        if db.fetch_one(conn, "SELECT 1 FROM attribut WHERE code = ?", (code,)):
            raise Conflit(f"L'attribut « {code} » existe déjà.")
        ordre = conn.execute("SELECT COALESCE(MAX(ordre), 0) + 1 FROM attribut").fetchone()[0]
        db.insert_row(
            conn,
            "attribut",
            {
                "code": code,
                "libelle": valeurs["libelle"].strip(),
                "type": valeurs["type"],
                "unite": (valeurs.get("unite") or "").strip() or None,
                "ordre": ordre,
            },
        )
        journal.write_journal(conn, "attribut", code, "creation", None, "créé")
    return get_attribut(conn, code)


def patch_attribut(conn: sqlite3.Connection, code: str, modifications: dict[str, Any]) -> dict:
    """Renomme, change l'unité, l'ordre ou l'état actif ; le code et le type restent."""
    with db.transaction(conn):
        get_attribut(conn, code)
        if "unite" in modifications:
            modifications = {
                **modifications,
                "unite": (modifications["unite"] or "").strip() or None,
            }
        journal.update_with_journal(conn, "attribut", code, modifications, CHAMPS_ATTRIBUT)
    return get_attribut(conn, code)


def create_valeur(conn: sqlite3.Connection, code: str, libelle: str) -> dict:
    """Ajoute une valeur possible à un attribut de type liste."""
    valeur_code = listes.code_depuis_libelle(libelle)
    with db.transaction(conn):
        attribut = get_attribut(conn, code)
        if attribut["type"] != "liste":
            raise ErreurMetier(f"« {attribut['libelle']} » n'est pas un attribut de type liste.")
        if db.fetch_one(
            conn,
            "SELECT 1 FROM attribut_valeur WHERE attribut_code = ? AND code = ?",
            (code, valeur_code),
        ):
            raise Conflit(f"La valeur « {valeur_code} » existe déjà pour {attribut['libelle']}.")
        ordre = conn.execute(
            "SELECT COALESCE(MAX(ordre), 0) + 1 FROM attribut_valeur WHERE attribut_code = ?",
            (code,),
        ).fetchone()[0]
        db.insert_row(
            conn,
            "attribut_valeur",
            {
                "attribut_code": code,
                "code": valeur_code,
                "libelle": libelle.strip(),
                "ordre": ordre,
            },
        )
        journal.write_journal(
            conn, "attribut_valeur", f"{code}:{valeur_code}", "creation", None, "créée"
        )
    return get_attribut(conn, code)


def patch_valeur(
    conn: sqlite3.Connection, code: str, valeur_code: str, modifications: dict[str, Any]
) -> dict:
    """Renomme, ordonne ou désactive une valeur possible ; son code stocké ne change pas."""
    with db.transaction(conn):
        actuelle = db.fetch_one(
            conn,
            "SELECT * FROM attribut_valeur WHERE attribut_code = ? AND code = ?",
            (code, valeur_code),
        )
        if actuelle is None:
            raise Introuvable(f"Valeur « {valeur_code} » introuvable pour l'attribut {code}.")
        requetes = {
            "libelle": "UPDATE attribut_valeur SET libelle = ?"
            " WHERE attribut_code = ? AND code = ?",
            "ordre": "UPDATE attribut_valeur SET ordre = ? WHERE attribut_code = ? AND code = ?",
            "actif": "UPDATE attribut_valeur SET actif = ? WHERE attribut_code = ? AND code = ?",
        }
        for cle in CHAMPS_VALEUR:
            if cle not in modifications or modifications[cle] == actuelle[cle]:
                continue
            conn.execute(requetes[cle], (modifications[cle], code, valeur_code))
            journal.write_journal(
                conn,
                "attribut_valeur",
                f"{code}:{valeur_code}",
                cle,
                actuelle[cle],
                modifications[cle],
            )
    return get_attribut(conn, code)


# --- Valeurs des composants ----------------------------------------------------------------------


def lire_nombre(brut: Any) -> float | None:
    """Nombre saisi (15, « 3,3 », « 24 V ») ; None s'il est illisible."""
    if isinstance(brut, bool):
        return None
    if isinstance(brut, int | float):
        return float(brut)
    texte = re.sub(r"[\s  ]", "", str(brut)).replace(",", ".")
    correspondance = re.match(r"^[-+]?\d+(\.\d+)?", texte)
    if correspondance is None or not re.fullmatch(r"[-+]?\d+(\.\d+)?[^\d]*", texte):
        return None
    return float(correspondance.group(0))


def lire_booleen(brut: Any) -> str | None:
    """'1' ou '0' ; None si la saisie n'est ni oui ni non."""
    if isinstance(brut, bool):
        return "1" if brut else "0"
    texte = str(brut).strip().lower()
    if texte in VRAI:
        return "1"
    if texte in FAUX:
        return "0"
    return None


def normalize(attribut: dict, brut: Any, actuelle: Any = None) -> tuple[str | None, float | None]:
    """Convertit une saisie en (valeur_texte, valeur_nombre) ; ErreurMetier si invalide.

    Une valeur de liste désactivée n'est acceptée que si c'est déjà celle du composant.
    """
    nom = attribut["libelle"]
    if attribut["type"] == "nombre":
        nombre = lire_nombre(brut)
        if nombre is None:
            raise ErreurMetier(f"{nom} : « {brut} » n'est pas un nombre.")
        return None, nombre
    if attribut["type"] == "booleen":
        booleen = lire_booleen(brut)
        if booleen is None:
            raise ErreurMetier(f"{nom} : « {brut} » ne vaut ni oui ni non.")
        return booleen, None
    texte = str(brut).strip()
    if not texte:
        raise ErreurMetier(f"{nom} : valeur vide.")
    if attribut["type"] == "liste":
        valeur = next((v for v in attribut["valeurs"] if v["code"] == texte), None)
        if valeur is None:
            raise ErreurMetier(f"{nom} : « {texte} » n'est pas une valeur de la liste.")
        if not valeur["actif"] and texte != actuelle:
            raise ErreurMetier(f"{nom} : « {valeur['libelle']} » est désactivée.")
    return texte, None


def get_valeurs(conn: sqlite3.Connection, composant_id: str) -> dict[str, Any]:
    """Valeurs d'un composant : {code: nombre ou texte}."""
    return valeurs_par_composant(conn, [composant_id]).get(composant_id, {})


def valeurs_par_composant(
    conn: sqlite3.Connection, ids: list[str] | None = None
) -> dict[str, dict[str, Any]]:
    """Valeurs de tous les composants (ou de ceux listés), indexées par composant puis code."""
    lignes = db.fetch_all(conn, "SELECT * FROM composant_attribut")
    voulus = set(ids) if ids is not None else None
    resultat: dict[str, dict[str, Any]] = {}
    for ligne in lignes:
        if voulus is not None and ligne["composant_id"] not in voulus:
            continue
        valeur = (
            ligne["valeur_nombre"] if ligne["valeur_nombre"] is not None else ligne["valeur_texte"]
        )
        resultat.setdefault(ligne["composant_id"], {})[ligne["attribut_code"]] = valeur
    return resultat


def set_valeurs(
    conn: sqlite3.Connection,
    composant_id: str,
    valeurs: dict[str, Any],
    origine: str = journal.ORIGINE_INTERFACE,
    lot_id: int | None = None,
) -> dict[str, Any]:
    """Enregistre des valeurs (None efface) avec journal ; à appeler dans une transaction.

    Renvoie les attributs réellement modifiés.
    """
    actuelles = get_valeurs(conn, composant_id)
    changes = {}
    for code, brut in valeurs.items():
        attribut = get_attribut(conn, code)
        actuelle = actuelles.get(code)
        vide = brut is None or (isinstance(brut, str) and not brut.strip())
        if vide:
            if actuelle is None:
                continue
            conn.execute(
                "DELETE FROM composant_attribut WHERE composant_id = ? AND attribut_code = ?",
                (composant_id, code),
            )
            nouvelle = None
        else:
            if not attribut["actif"]:
                raise ErreurMetier(f"L'attribut « {attribut['libelle']} » est désactivé.")
            texte, nombre = normalize(attribut, brut, actuelle)
            nouvelle = nombre if nombre is not None else texte
            if actuelle is not None and not journal.differe(actuelle, nouvelle):
                continue
            conn.execute(
                "INSERT INTO composant_attribut (composant_id, attribut_code, valeur_texte,"
                " valeur_nombre) VALUES (?, ?, ?, ?) ON CONFLICT (composant_id, attribut_code)"
                " DO UPDATE SET valeur_texte = excluded.valeur_texte,"
                " valeur_nombre = excluded.valeur_nombre",
                (composant_id, code, texte, nombre),
            )
        journal.write_journal(
            conn,
            "composant_attribut",
            f"{composant_id}:{code}",
            code,
            actuelle,
            nouvelle,
            origine,
            lot_id,
        )
        changes[code] = nouvelle
    return changes


def libelles_valeurs(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """Libellé de chaque valeur de liste, par (attribut, code)."""
    return {
        (v["attribut_code"], v["code"]): v["libelle"]
        for v in db.fetch_all(conn, "SELECT attribut_code, code, libelle FROM attribut_valeur")
    }


def affichage(attribut: dict, valeur: Any, libelles: dict[tuple[str, str], str]) -> Any:
    """Valeur lisible pour un export : libellé de liste, Oui/Non, nombre tel quel."""
    if valeur is None:
        return None
    if attribut["type"] == "liste":
        return libelles.get((attribut["code"], valeur), valeur)
    if attribut["type"] == "booleen":
        return "Oui" if valeur == "1" else "Non"
    return valeur
