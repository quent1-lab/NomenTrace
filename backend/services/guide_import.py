"""Consigne à donner à un outil d'IA pour convertir l'Excel d'une équipe au modèle vierge.

La consigne reprend le vocabulaire actuel du projet (blocs, listes, fournisseurs, attributs)
pour que l'IA choisisse des valeurs existantes plutôt que d'en inventer : une valeur
inconnue serait proposée à la création par l'import, une par une.
"""

import re
import sqlite3

from backend.services import attributs, blocs, fournisseurs, import_colonnes, listes, parametres

# Listes dont les valeurs sont données à l'IA, avec la colonne du modèle qui les porte.
LISTES_MODELE: dict[str, str] = {
    "mode_appro": "Mode appro",
    "statut_choix": "Statut choix",
    "statut_appro": "Statut appro",
    "criticite": "Criticité",
}
FOURNISSEURS_MAX = 80

# Le fichier d'une équipe ne dit presque jamais le bloc de chaque composant : l'IA analyse
# d'abord, propose sa répartition et pose ses questions, puis attend la réponse.
AVANT = """Avant de remplir quoi que ce soit, analyse mon fichier et réponds-moi d'abord :
a. Les colonnes de mon fichier que tu as reconnues, et vers quelle colonne du modèle chacune
   va ; celles que tu ne sais pas où mettre.
b. Les blocs : mon fichier ne les nomme sans doute pas comme Nomentrace. Propose un bloc de
   la liste ci-dessous pour chaque groupe de composants (par catégorie, onglet, fonction ou
   sous-système de mon fichier), avec ta raison, et signale ceux pour lesquels aucun bloc ne
   convient. N'invente aucun code de bloc : un bloc inconnu fait refuser la ligne.
c. Les informations qui manquent ou sont ambiguës : prix HT ou TTC, quantités par
   composant ou par ensemble, rechange, stock déjà disponible, fournisseurs, unités des
   caractéristiques, lignes qui ressemblent à des doublons ou à des sous-totaux.
d. Tes questions, numérotées.
Attends mes réponses. Ne remplis le modèle qu'après mon accord sur la répartition par bloc
et sur tes questions."""

REGLES = """Règles :
1. Une ligne par composant différent. Ne fusionne pas deux références différentes ; si la
   même référence apparaît plusieurs fois, garde une seule ligne et additionne les
   quantités, en le signalant.
2. Remplis seulement la feuille « Composants », sous les en-têtes existants, sans les
   modifier ni en ajouter. Laisse la colonne ID vide : Nomentrace attribue les identifiants.
   Ne touche pas aux autres feuilles.
3. Obligatoires : Bloc, Fonction, Désignation, Mode appro, Qté besoin (nombre entier).
4. Pour Bloc, Mode appro, Statut choix, Statut appro, Criticité, Fournisseur et les
   caractéristiques à liste : reprends exactement une valeur ci-dessous. Si aucune ne
   convient, laisse la cellule vide et signale la ligne, sauf pour Fournisseur où un
   nouveau nom est accepté.
5. N'invente rien : une information absente de mon fichier reste vide.
6. Lien produit : l'adresse web seule (https://…). Réf fabricant : la référence seule,
   jamais une adresse web ni une phrase. Fonction : à quoi sert le composant ;
   Désignation : ce qu'il est, en quelques mots.
7. PU relevé : le prix unitaire tel qu'il est écrit, sans symbole €, et Base prix « HT » ou
   « TTC » selon ce qu'indique mon fichier (« HT » s'il ne dit rien).
8. Qté déjà disponible : les pièces déjà possédées (stock, prêt), seulement si mon fichier
   le dit.
9. Ensemble et Qté dans cet ensemble : facultatifs, seulement si mon fichier dit où le
   composant est monté.
10. Rends le classeur complété, puis la liste des lignes ignorées, douteuses ou
    regroupées, avec la raison."""


def _bloc_texte(conn: sqlite3.Connection) -> str:
    lignes = [f"- {b['code']} : {b['nom']}" for b in blocs.list_blocs(conn)]
    return "\n".join(lignes) if lignes else "- (aucun bloc créé : à créer avant l'import)"


def _listes_texte(conn: sqlite3.Connection) -> str:
    toutes = listes.list_listes(conn)
    sections = []
    for liste, colonne in LISTES_MODELE.items():
        valeurs = [v["libelle"] for v in toutes.get(liste, []) if v["actif"]]
        sections.append(f"- {colonne} : {' | '.join(valeurs) or '(vide)'}")
    return "\n".join(sections)


def _fournisseurs_texte(conn: sqlite3.Connection) -> str:
    noms = [f["nom"] for f in fournisseurs.list_fournisseurs(conn)]
    if not noms:
        return "- (aucun : reprends les noms de mon fichier)"
    texte = " | ".join(noms[:FOURNISSEURS_MAX])
    reste = len(noms) - FOURNISSEURS_MAX
    return f"- {texte}" + (f" (et {reste} autres)" if reste > 0 else "")


def _attributs_texte(conn: sqlite3.Connection) -> str:
    lignes = []
    for a in attributs.list_attributs(conn, actifs_seulement=True):
        unite = f" en {a['unite']}" if a["unite"] else ""
        choix = " | ".join(v["libelle"] for v in a["valeurs"] if v.get("actif", 1))
        nature = {
            "nombre": f"un nombre{unite}, sans l'unité",
            "booleen": "Oui ou Non",
            "texte": "un texte court",
            "liste": f"une valeur parmi {choix}",
        }[a["type"]]
        lignes.append(f"- {attributs.entete(a)} : {nature}")
    return "\n".join(lignes) if lignes else "- (aucune)"


def build_prompt(conn: sqlite3.Connection) -> str:
    """Consigne complète, prête à copier, pour le modèle vierge du projet."""
    projet = parametres.get_parametre(conn, "nom_projet") or "notre projet"
    colonnes = ", ".join(c.entete for c in import_colonnes.COLONNES)
    return "\n\n".join(
        [
            f"Je te donne deux fichiers Excel : la nomenclature de mon équipe pour le projet "
            f"« {projet} », dans notre format, et le modèle vierge de l'outil Nomentrace. "
            "Recopie chaque composant de mon fichier dans le modèle, en suivant les règles, "
            "mais pas tout de suite : commence par l'analyse ci-dessous.",
            re.sub(r"\n\s{2,}", " ", AVANT),
            f"Colonnes du modèle : {colonnes}, puis les caractéristiques, Ensemble et Qté "
            "dans cet ensemble.",
            # Une règle par ligne : les retours à la ligne du code ne servent qu'à la lecture.
            re.sub(r"\n\s{2,}", " ", REGLES),
            f"Blocs (colonne Bloc, mets le code) :\n{_bloc_texte(conn)}",
            f"Valeurs des listes :\n{_listes_texte(conn)}",
            f"Fournisseurs déjà connus (même orthographe) :\n{_fournisseurs_texte(conn)}",
            f"Caractéristiques (colonnes après Note technique) :\n{_attributs_texte(conn)}",
        ]
    )
