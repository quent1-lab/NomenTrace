"""Mots de passe, connexion et sessions, dans la base des comptes.

Rien n'y est stocké en clair : le mot de passe est haché par scrypt avec un sel propre, et
les jetons de session ou d'invitation ne sont conservés que par leur empreinte SHA-256. Un
vol de la base des comptes ne donne donc ni mot de passe ni session utilisable.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend import db
from backend.erreurs import ErreurMetier

journal_log = logging.getLogger(__name__)

# Paramètres scrypt recommandés par l'OWASP (N = 2^17, r = 8, p = 1 : 128 Mio par calcul).
# Ils sont écrits dans chaque empreinte : les changer n'invalide pas les mots de passe existants.
SCRYPT_N: int = 2**17
SCRYPT_R: int = 8
SCRYPT_P: int = 1
TAILLE_SEL: int = 16
# Deux calculs à la fois au plus : une rafale de tentatives ne peut pas épuiser la mémoire.
_calculs = threading.BoundedSemaphore(2)

# Un mot de passe est haché dans un fil du serveur, et l'opération est lente à dessein
# (scrypt). Sans limite, une rafale de connexions occuperait tous les fils et bloquerait le
# reste de l'application. On borne donc le nombre de connexions et d'invitations traitées en
# même temps : au-delà, la requête est refusée aussitôt (503) sans occuper un fil, plutôt que
# de faire attendre tout le monde. La borne dépasse le nombre de calculs simultanés pour
# absorber quelques connexions légitimes en même temps.
CONNEXIONS_SIMULTANEES: int = 6
_places = threading.BoundedSemaphore(CONNEXIONS_SIMULTANEES)


class ServeurOccupe(ErreurMetier):
    """Trop de connexions en cours en même temps ; réessayer suffit."""

    def __init__(self) -> None:
        super().__init__(
            "Trop de connexions au même moment. Patienter quelques secondes et réessayer.", 503
        )


@contextmanager
def limiter_connexions() -> Iterator[None]:
    """Réserve une place de traitement d'authentification, ou refuse tout de suite."""
    if not _places.acquire(blocking=False):
        raise ServeurOccupe()
    try:
        yield
    finally:
        _places.release()


LONGUEUR_MIN: int = 12
LONGUEUR_MAX: int = 128

DUREE_SESSION = timedelta(days=14)
# Cinq échecs bloquent le couple compte + adresse IP : un tiers qui tape de mauvais mots de
# passe sur le compte de quelqu'un d'autre ne bloque que lui-même. Une limite bien plus large
# par compte seul arrête une attaque répartie sur de nombreuses adresses.
ECHECS_MAX_COMPTE_ADRESSE: int = 5
ECHECS_MAX_COMPTE: int = 50
DUREE_BLOCAGE = timedelta(minutes=15)
# Une école sort souvent par une seule adresse IP : la limite par adresse est plus large que
# celle par compte, pour qu'une personne qui se trompe ne bloque pas toute l'équipe.
ECHECS_MAX_ADRESSE: int = 20

MESSAGE_ECHEC = "Identifiant ou mot de passe incorrect."


class TropDeTentatives(ErreurMetier):
    """Connexion refusée le temps du blocage, même avec le bon mot de passe."""

    def __init__(self) -> None:
        super().__init__("Trop de tentatives de connexion. Réessayer dans quelques minutes.", 429)


def maintenant() -> datetime:
    return datetime.now().replace(microsecond=0)


def horodatage(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def empreinte_jeton(jeton: str) -> str:
    """Empreinte stockée d'un jeton de session ou d'invitation."""
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def nouveau_jeton() -> str:
    """Jeton aléatoire de 256 bits, transmis une fois au navigateur ou à l'administrateur."""
    return secrets.token_urlsafe(32)


# --- Mots de passe ------------------------------------------------------------------------------


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode("ascii")


def _scrypt(mot_de_passe: str, sel: bytes, n: int, r: int, p: int) -> bytes:
    with _calculs:
        return hashlib.scrypt(
            mot_de_passe.encode("utf-8"), salt=sel, n=n, r=r, p=p, maxmem=256 * n * r, dklen=32
        )


def hash_mot_de_passe(mot_de_passe: str) -> str:
    """Empreinte « scrypt$N$r$p$sel$hash », sel et hash en base 64."""
    sel = secrets.token_bytes(TAILLE_SEL)
    empreinte = _scrypt(mot_de_passe, sel, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(sel)}${_b64(empreinte)}"


def verify_mot_de_passe(mot_de_passe: str, stockee: str) -> bool:
    """Compare en temps constant ; une empreinte illisible ne valide jamais rien."""
    try:
        algo, n, r, p, sel, attendue = stockee.split("$")
        if algo != "scrypt":
            return False
        calculee = _scrypt(mot_de_passe, base64.b64decode(sel), int(n), int(r), int(p))
    except ValueError:
        journal_log.warning("Empreinte de mot de passe illisible dans la base des comptes.")
        return False
    return hmac.compare_digest(calculee, base64.b64decode(attendue))


_EMPREINTE_LEURRE: str | None = None


def _leurre() -> str:
    """Empreinte factice : un identifiant inconnu coûte le même temps qu'un vrai."""
    global _EMPREINTE_LEURRE
    if _EMPREINTE_LEURRE is None or not _EMPREINTE_LEURRE.startswith(f"scrypt${SCRYPT_N}$"):
        _EMPREINTE_LEURRE = hash_mot_de_passe(secrets.token_urlsafe(16))
    return _EMPREINTE_LEURRE


# Exigences du mot de passe choisi par le lien d'invitation. La page de connexion les
# affiche et les coche pendant la saisie (static/js/connexion.js), mais c'est ce contrôle
# qui fait foi. Une phrase de passe d'au moins LONGUEUR_PHRASE caractères est dispensée des
# règles de composition : sa longueur la protège mieux qu'un mélange de symboles.
LONGUEUR_PHRASE: int = 20
CARACTERES_DISTINCTS_MIN: int = 6
# Mots de passe parmi les plus essayés : refusés tels quels, même assez longs.
COURANTS: frozenset[str] = frozenset(
    {
        "motdepasse", "password", "azerty", "qwerty", "123456789", "1234567890",
        "abcdefghijkl", "nomentrace", "bonjour", "soleil", "doudou", "loveyou",
        "iloveyou", "admin", "administrateur", "azertyuiop", "qwertyuiop",
    }
)  # fmt: skip


def _simplifie(texte: str) -> str:
    return "".join(c for c in texte.lower() if c.isalnum())


def exigences_mot_de_passe(
    mot_de_passe: str, identifiant: str, nom: str = ""
) -> list[tuple[str, bool]]:
    """Chaque exigence avec son libellé et si elle est remplie."""
    phrase = len(mot_de_passe) >= LONGUEUR_PHRASE
    compose = phrase or (
        any(c.islower() for c in mot_de_passe)
        and any(c.isupper() for c in mot_de_passe)
        and any(c.isdigit() for c in mot_de_passe)
        and any(not c.isalnum() for c in mot_de_passe)
    )
    simple = _simplifie(mot_de_passe)
    personnels = [
        p for p in (_simplifie(identifiant.split("@")[0]), _simplifie(nom)) if len(p) >= 3
    ]
    # « Motdepasse2026! » est courant : une fois le mot connu retiré, il reste trop peu.
    courant = any(m in simple and len(simple.replace(m, "", 1)) < 6 for m in COURANTS)
    return [
        (f"{LONGUEUR_MIN} caractères au moins", LONGUEUR_MIN <= len(mot_de_passe) <= LONGUEUR_MAX),
        (
            "une minuscule, une majuscule, un chiffre et un caractère spécial, "
            f"ou une phrase de {LONGUEUR_PHRASE} caractères au moins",
            compose,
        ),
        ("ni l'adresse mail ni le nom", not any(p in simple for p in personnels)),
        (
            f"{CARACTERES_DISTINCTS_MIN} caractères différents au moins,"
            " pas un mot de passe courant",
            len(set(mot_de_passe)) >= CARACTERES_DISTINCTS_MIN and not courant,
        ),
    ]


def check_mot_de_passe(mot_de_passe: str, identifiant: str, nom: str = "") -> None:
    """Refuse un mot de passe qui ne remplit pas toutes les exigences, en les citant."""
    if len(mot_de_passe) > LONGUEUR_MAX:
        raise ErreurMetier(f"Le mot de passe ne doit pas dépasser {LONGUEUR_MAX} caractères.")
    manquantes = [
        libelle
        for libelle, remplie in exigences_mot_de_passe(mot_de_passe, identifiant, nom)
        if not remplie
    ]
    if manquantes:
        raise ErreurMetier("Mot de passe refusé. Il faut : " + " ; ".join(manquantes) + ".")


def set_mot_de_passe(conn: sqlite3.Connection, utilisateur_id: int, mot_de_passe: str) -> None:
    """Remplace le mot de passe ; à appeler dans une transaction."""
    conn.execute(
        "DELETE FROM identite WHERE utilisateur_id = ? AND fournisseur = 'mot_de_passe'",
        (utilisateur_id,),
    )
    conn.execute(
        "INSERT INTO identite (utilisateur_id, fournisseur, sujet, secret)"
        " VALUES (?, 'mot_de_passe', ?, ?)",
        (utilisateur_id, str(utilisateur_id), hash_mot_de_passe(mot_de_passe)),
    )


# --- Limitation des tentatives ------------------------------------------------------------------


class Limiteur:
    """Échecs récents par clé (adresse IP ou identifiant), sur une fenêtre glissante.

    En mémoire : un seul processus sert l'application. La limite s'applique de la même façon
    à un identifiant inconnu, pour que le blocage ne révèle pas quels comptes existent.
    """

    def __init__(self, maximum: int, fenetre: timedelta = DUREE_BLOCAGE) -> None:
        self.maximum = maximum
        self.fenetre = fenetre.total_seconds()
        self._echecs: dict[str, deque[float]] = {}
        self._verrou = threading.Lock()

    def _recents(self, cle: str, instant: float) -> deque[float]:
        echecs = self._echecs.setdefault(cle, deque())
        while echecs and instant - echecs[0] > self.fenetre:
            echecs.popleft()
        return echecs

    def bloque(self, cle: str) -> bool:
        with self._verrou:
            return len(self._recents(cle, time.monotonic())) >= self.maximum

    def noter_echec(self, cle: str) -> None:
        with self._verrou:
            instant = time.monotonic()
            self._recents(cle, instant).append(instant)
            if len(self._echecs) > 10_000:
                self._echecs = {c: e for c, e in self._echecs.items() if e}

    def oublier(self, cle: str) -> None:
        with self._verrou:
            self._echecs.pop(cle, None)


@dataclass
class Limiteurs:
    """Les limites d'une instance : par adresse IP, par couple compte + adresse, par compte."""

    adresses: Limiteur = field(default_factory=lambda: Limiteur(ECHECS_MAX_ADRESSE))
    couples: Limiteur = field(default_factory=lambda: Limiteur(ECHECS_MAX_COMPTE_ADRESSE))
    identifiants: Limiteur = field(default_factory=lambda: Limiteur(ECHECS_MAX_COMPTE))


# --- Connexion ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionOuverte:
    jeton: str
    utilisateur_id: int
    expire_le: datetime


def login(
    conn: sqlite3.Connection,
    limiteurs: Limiteurs,
    identifiant: str,
    mot_de_passe: str,
    adresse: str,
) -> int:
    """Vérifie identifiant et mot de passe ; renvoie l'id de l'utilisateur.

    Le message d'échec est le même que l'identifiant existe ou non, et le temps de réponse
    aussi : un calcul scrypt est fait dans tous les cas.
    """
    cle = identifiant.strip().lower()
    couple = f"{cle}|{adresse}"
    if (
        limiteurs.adresses.bloque(adresse)
        or limiteurs.couples.bloque(couple)
        or limiteurs.identifiants.bloque(cle)
    ):
        raise TropDeTentatives()
    utilisateur = db.fetch_one(
        conn,
        "SELECT u.id, u.actif, i.secret FROM utilisateur u LEFT JOIN identite i"
        " ON i.utilisateur_id = u.id AND i.fournisseur = 'mot_de_passe'"
        " WHERE u.identifiant = ?",
        (cle,),
    )
    secret = utilisateur["secret"] if utilisateur else None
    valide = verify_mot_de_passe(mot_de_passe, secret or _leurre()) and secret is not None
    if not valide:
        limiteurs.adresses.noter_echec(adresse)
        limiteurs.couples.noter_echec(couple)
        limiteurs.identifiants.noter_echec(cle)
        journal_log.info("Connexion refusée pour %r depuis %s.", cle, adresse)
        raise ErreurMetier(MESSAGE_ECHEC, 401)
    limiteurs.couples.oublier(couple)
    if not utilisateur["actif"]:
        raise ErreurMetier("Ce compte est désactivé. S'adresser à un administrateur.", 403)
    return int(utilisateur["id"])


def open_session(conn: sqlite3.Connection, utilisateur_id: int, adresse: str) -> SessionOuverte:
    """Crée une session ; le jeton en clair n'existe que dans la réponse au navigateur."""
    jeton = nouveau_jeton()
    debut = maintenant()
    fin = debut + DUREE_SESSION
    with db.transaction(conn):
        conn.execute("DELETE FROM session WHERE expire_le <= ?", (horodatage(debut),))
        conn.execute(
            "INSERT INTO session (empreinte, utilisateur_id, expire_le, adresse_ip)"
            " VALUES (?, ?, ?, ?)",
            (empreinte_jeton(jeton), utilisateur_id, horodatage(fin), adresse),
        )
        conn.execute(
            "UPDATE utilisateur SET derniere_connexion = ? WHERE id = ?",
            (horodatage(debut), utilisateur_id),
        )
    journal_log.info("Session ouverte pour l'utilisateur %d depuis %s.", utilisateur_id, adresse)
    return SessionOuverte(jeton, utilisateur_id, fin)


def get_session(conn: sqlite3.Connection, jeton: str) -> int | None:
    """Utilisateur actif d'une session valide, ou None."""
    ligne = db.fetch_one(
        conn,
        "SELECT s.utilisateur_id FROM session s JOIN utilisateur u ON u.id = s.utilisateur_id"
        " WHERE s.empreinte = ? AND s.expire_le > ? AND u.actif = 1",
        (empreinte_jeton(jeton), horodatage(maintenant())),
    )
    return int(ligne["utilisateur_id"]) if ligne else None


def close_session(conn: sqlite3.Connection, jeton: str) -> None:
    with db.transaction(conn):
        conn.execute("DELETE FROM session WHERE empreinte = ?", (empreinte_jeton(jeton),))


def close_sessions(conn: sqlite3.Connection, utilisateur_id: int) -> None:
    """Ferme toutes les sessions d'un utilisateur ; à appeler dans une transaction."""
    conn.execute("DELETE FROM session WHERE utilisateur_id = ?", (utilisateur_id,))
