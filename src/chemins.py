# -*- coding: utf-8 -*-
"""
Resolution des chemins de fichiers, robuste que DAN tourne :
- en developpement (streamlit run src/dashboard.py), ou
- empaquete en executable PyInstaller --onefile.

En mode --onefile, PyInstaller extrait les ressources embarquees (mapping/,
referentiels/, templates/) dans un dossier temporaire propre a chaque
lancement (expose via sys._MEIPASS), DIFFERENT du dossier de travail
courant -- d'ou l'erreur "table de correspondance introuvable" quand
l'executable est lance depuis un dossier qui ne contient pas par hasard
une copie de ces dossiers.

Deux cas bien distincts :

1. Ressources EN LECTURE SEULE livrees avec l'application (mapping,
   referentiels, templates) -> chemin_ressource() : va chercher dans le
   dossier temporaire d'extraction (sys._MEIPASS) en mode --onefile.

2. Donnees EN LECTURE-ECRITURE propres a l'utilisateur (historique,
   configuration, journal d'erreurs, dans data/) -> chemin_donnees() :
   ne doit JAMAIS pointer vers sys._MEIPASS, ce dossier temporaire etant
   supprime a la fermeture de l'executable -- l'historique et la
   configuration seraient perdus a chaque relance. Pointe a la place vers
   le dossier contenant l'executable lui-meme.
"""
import os
import sys


def _en_mode_executable():
    """Vrai si DAN tourne comme executable PyInstaller (--onefile ou --onedir)."""
    return getattr(sys, "frozen", False)


def chemin_ressource(chemin_relatif):
    """
    Resout le chemin d'une ressource EN LECTURE SEULE livree avec DAN
    (mapping/mapping_risques.xlsx, referentiels/logo.png,
    templates/rapport_general.docx, etc.).
    """
    if _en_mode_executable():
        base = sys._MEIPASS
    else:
        base = os.getcwd()
    return os.path.join(base, chemin_relatif)


def chemin_donnees(chemin_relatif):
    """
    Resout le chemin d'un fichier ou dossier EN LECTURE-ECRITURE propre a
    l'utilisateur (dans data/ : historique.json, configuration.json,
    erreurs.log ; ou les dossiers de versions precedentes du mapping et
    du guide). Doit survivre entre deux lancements de l'executable --
    place donc ces chemins a cote de l'executable lui-meme, jamais dans
    le dossier temporaire d'extraction.

    Fonction volontairement PURE (aucune creation de dossier ici) : chaque
    appelant gere deja lui-meme sa propre creation de dossier au bon
    endroit (fichier -> son dossier parent ; dossier -> lui-meme), a
    l'identique de son fonctionnement d'origine.
    """
    if _en_mode_executable():
        base = os.path.dirname(sys.executable)
    else:
        base = os.getcwd()
    return os.path.join(base, chemin_relatif)
