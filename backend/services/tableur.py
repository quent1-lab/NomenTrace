"""Outils communs aux classeurs Excel produits par Nomentrace."""

from openpyxl import Workbook


def neutraliser_formules(classeur: Workbook) -> None:
    """Écrit comme du texte toute valeur qui commence par « = ».

    openpyxl transforme en formule une chaîne commençant par « = ». Un texte saisi par un
    utilisateur (une désignation, un commentaire) deviendrait alors une formule exécutée à
    l'ouverture du classeur par un autre : aucune cellule exportée n'est une formule.
    """
    for feuille in classeur.worksheets:
        for ligne in feuille.iter_rows():
            for cellule in ligne:
                if cellule.data_type == "f":
                    cellule.data_type = "s"
