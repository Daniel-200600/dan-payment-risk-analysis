# Tests automatisés de DAN

Cette suite couvre les zones du code où des bugs réels ont été trouvés et
corrigés au cours du développement — chaque test existe pour empêcher une
régression précise de revenir silencieusement.

## Installation (une seule fois)

Depuis un terminal, dans le dossier `DAN/`, environnement virtuel activé :

```
pip install pytest
```

## Lancer tous les tests

```
pytest
```

Résultat attendu : une ligne verte `209 passed` (ou plus, si de nouveaux
tests ont été ajoutés depuis). Si une ligne rouge `FAILED` apparaît, c'est
qu'une modification récente a cassé quelque chose qui fonctionnait avant —
le message d'erreur indique quel test échoue et pourquoi.

## Lancer un seul fichier de tests

```
pytest tests/test_donnees.py
```

## Lancer un seul test précis

```
pytest tests/test_donnees.py::TestSurvenance::test_variantes_de_survenance
```

## Organisation des fichiers

| Fichier | Ce qu'il couvre |
|---|---|
| `test_donnees.py` | Lecture des fichiers, détection du système par contenu, traitement RAS/NaN, calcul du score |
| `test_interpretation.py` | Cohérence du niveau de risque (badge, jauge, textes) |
| `test_historique.py` | Déduplication des rapports, effacement, détection d'import en double |
| `test_referentiel.py` | Mise à jour du mapping et du Guide de surveillance, sauvegarde/restauration |

## Quand relancer les tests

À chaque fois que vous modifiez un fichier dans `src/logic/` —
avant de considérer une correction comme terminée. Un test qui passe ne
garantit pas l'absence de bug, mais un test qui échoue signale une
régression avec certitude.

## Bonne pratique

Si vous trouvez un nouveau bug, le réflexe utile est : écrire d'abord un
test qui échoue à cause de ce bug, corriger le code, puis vérifier que le
test passe. Cela garantit que ce bug précis ne pourra plus jamais revenir
sans être détecté immédiatement.
