# -*- coding: utf-8 -*-
import streamlit as st
from style import entete_page
from logic.configuration import charger_configuration


def afficher():
    entete_page("Aide", "Guide d'utilisation de DAN")
    config = charger_configuration()

    onglets = st.tabs([
        "ℹ️ Présentation", "🧭 Guide d'utilisation", "📊 Comprendre les scores",
        "❓ FAQ", "✅ Bonnes pratiques", "✉️ Contact",
    ])

    with onglets[0]:
        st.subheader("Présentation de DAN")
        st.markdown(f"""
**Objectif du logiciel** — DAN consolide les indicateurs de surveillance des
quatre systèmes de paiement (SYGMA, SWIFT, SYSTAC, RESEAU) en un score de
risque unique par participant, enrichi d'une analyse qualitative automatique,
et génère le rapport mensuel de surveillance sans intervention manuelle.

**Fonctionnement général** — chaque mois, les fichiers Excel de reporting sont
importés dans DAN, qui les rapproche du référentiel de risque, calcule un
score, l'interprète en langage clair, et produit un ou plusieurs rapports Word.

Toutes les données (historique, configuration) sont stockées localement sur cet
ordinateur, aucune donnée ne transite par un service externe.

*Version {config['version']} — {config['nom_institution']}, {config['direction']}.*
        """)

    with onglets[1]:
        st.subheader("Guide d'utilisation, étape par étape")
        etapes = [
            ("Étape 1 — Importer les reportings",
             "Allez sur « Import des reportings ». Deux façons de déposer vos fichiers "
             "Excel (SYGMA, SWIFT, SYSTAC, RESEAU) : en les glissant directement, ou en "
             "activant le bascule « Déposer un dossier entier » pour choisir un dossier "
             "complet (arborescence Pays / Banque / reportings) — DAN lit alors tous les "
             "fichiers Excel qu'il contient, à n'importe quelle profondeur, et peut ignorer "
             "sans problème les autres documents mélangés dedans (référentiels, archives...). "
             "Vous pouvez cliquer plusieurs fois sur le sélecteur pour ajouter plusieurs "
             "dossiers avant de lancer l'import. DAN détecte automatiquement le système et "
             "le site (siège/agence) à partir du **contenu** du fichier (les références des "
             "événements, ex. RPSYSPA01) — le nom du fichier n'a pas besoin de suivre une "
             "convention particulière."),
            ("Étape 1 bis — Plusieurs pays dans un même lot",
             "Si votre lot contient les fichiers de plusieurs pays (un dossier de premier "
             "niveau par pays, ex. Cameroun/Banque_A/...), DAN les sépare automatiquement. "
             "La casse et les sigles usuels sont reconnus (CAMEROUN, Cameroun, CMR et cmr "
             "désignent tous le même pays). Cliquez sur l'unique bouton « 📊 Analyser le "
             "lot » : vous arrivez directement sur le Tableau de bord, où le filtre "
             "« Pays » propose tous les pays du lot — sélectionnez-en un ou plusieurs, "
             "puis validez pour afficher les résultats."),
            ("Étape 2 — Vérifier les données",
             "Le tableau récapitulatif affiché après import indique le nombre "
             "d'événements lus par fichier — vérifiez qu'aucun fichier n'est "
             "marqué « système non reconnu »."),
            ("Étape 3 — Analyser",
             "Allez sur « Analyse des incidents » pour obtenir un résumé automatique : "
             "principaux problèmes et causes probables des incidents survenus."),
            ("Étape 4 — Consulter le tableau de bord",
             "Le « Tableau de bord » affiche, pour chaque pays, l'interprétation du "
             "score, son évolution par mois et la répartition du risque par système, "
             "puis un graphique comparant l'évolution mensuelle de tous les pays "
             "sélectionnés sur un même graphique."),
            ("Étape 5 — Générer les rapports",
             "Sur « Génération des rapports », choisissez le rapport général "
             "consolidé (liste des incidents) ou le rapport d'activité, puis générez, prévisualisez et téléchargez en Word ou PDF."),
        ]
        for titre, texte in etapes:
            with st.expander(titre):
                st.write(texte)

    with onglets[2]:
        st.subheader("Comprendre les scores")
        st.markdown("""
**Le score de DAN n'est pas un pourcentage** — c'est une **gravité cumulée**,
sans plafond fixe à 100. Il se calcule à partir de trois éléments, pour
chaque événement suivi :

1. **La survenance** — l'événement s'est-il produit ce mois-ci (Oui) ou non ?
   Un événement non survenu ne contribue jamais au score.
2. **La récurrence** — combien de fois l'événement s'est-il produit ? Un
   événement répété pèse davantage, mais avec des rendements décroissants
   (un incident survenu 100 fois ne pèse pas 100 fois plus qu'un incident
   isolé — sinon un seul événement très fréquent écraserait tout le reste
   du score).
3. **Le niveau de risque** — chaque point du référentiel a un niveau
   (Critique, Majeur, Sensible, Faible), qui pèse plus ou moins lourd dans
   le calcul.

Le score global d'un participant est la somme de ces contributions sur tous
les événements survenus, tous systèmes confondus. **Plus il est élevé, plus
la situation est préoccupante** — mais il n'y a pas de maximum théorique :
un score de 40 n'est pas "presque plein", c'est une valeur à comparer aux
seuils ci-dessous.
        """)

        seuils_actuels = charger_configuration().get("seuils_gravite", [25, 10, 3, 0.5])
        s_crit, s_eleve, s_moyen, s_faible = seuils_actuels

        st.markdown("**Les 5 niveaux et leurs seuils actuels**")
        st.markdown(f"""
| Gravité cumulée | Niveau | Signification |
|---|---|---|
| {s_crit} et plus | ⚫ Critique | Dysfonctionnements majeurs ou répétés, intervention immédiate requise |
| {s_eleve} à {s_crit} | 🔴 Élevé | Incidents significatifs ou récurrents, investigation prioritaire |
| {s_moyen} à {s_eleve} | 🟠 Moyen | Anomalies nécessitant une surveillance renforcée |
| {s_faible} à {s_moyen} | 🟡 Faible | Écarts mineurs, surveillance normale |
| 0 à {s_faible} | 🟢 Très faible | Fonctionnement normal, simple surveillance |
        """)
        st.info(
            "ℹ️ Ces seuils sont **modifiables** dans Paramètres → « Seuils de score », "
            "selon vos propres besoins d'analyse — les valeurs ci-dessus sont celles "
            "actuellement configurées, pas une norme figée par DAN."
        )
        st.markdown("""
Chaque score affiché dans DAN (tableau de bord, rapports) est accompagné
d'une explication en langage clair de ce qu'il représente — jamais un
chiffre seul sans contexte.
        """)

    with onglets[3]:
        st.subheader("Questions fréquentes")
        faq = [
            ("Comment corriger le nombre de participants « Reçu » si l'estimation est fausse ?",
             "Dans Paramètres → « Participants attendus/reçus », le nombre attendu est "
             "toujours à votre charge (donnée institutionnelle), et le nombre reçu est "
             "estimé automatiquement à partir du dernier lot importé — vous pouvez le "
             "corriger manuellement dans la même page si l'estimation ne correspond pas "
             "à la réalité. La correction s'applique automatiquement au prochain rapport "
             "d'activité généré."),
            ("Pourquoi le graphique d'évolution n'apparaît-il pas dans mon rapport d'activité ?",
             "Ce graphique nécessite au moins deux analyses déjà enregistrées dans "
             "l'historique de DAN pour pouvoir tracer une tendance — il apparaît "
             "automatiquement dès que cette condition est remplie, sans action de votre part."),
            ("Pourquoi un système affiche-t-il « 0 » alors que j'ai importé son fichier ?",
             "Un score de 0 signifie qu'aucun événement n'est marqué « Survenu » ce "
             "mois-ci pour ce système — c'est un résultat normal, pas une erreur."),
            ("Comment DAN reconnaît-il à quel pays appartient un fichier ?",
             "Uniquement à partir du nom du dossier de premier niveau qui contenait le "
             "fichier lors d'un dépôt de dossier entier (ex. Cameroun/Banque_A/SYGMA.xlsx "
             "→ pays = Cameroun). Un fichier déposé isolément, sans dossier parent, n'a "
             "pas de pays connu et apparaît comme « INCONNU »."),
            ("Faut-il nommer les dossiers exactement « Cameroun », « Tchad »... ?",
             "Non — DAN reconnaît les variantes de casse (CAMEROUN, cameroun), les "
             "accents, et les sigles usuels (CMR, TD, RCA, COG, GAB, GNQ...). Un nom de "
             "dossier qui ne correspond à aucun des six pays de la CEMAC reste affiché "
             "tel quel, sans être masqué."),
            ("La Vue multi-participants n'affiche-t-elle vraiment que les 6 pays de la CEMAC ?",
             "Oui — Cameroun, Centrafrique, Congo, Gabon, Guinée Équatoriale et Tchad "
             "apparaissent systématiquement, y compris ceux n'ayant pas encore transmis "
             "(statut « Non transmis »). Aucune liste à charger : cet ensemble est fixe "
             "et intégré à DAN."),
            ("Le fichier que j'importe n'est pas reconnu, que faire ?",
             "DAN détecte le système à partir des références des événements dans le "
             "fichier (ex. RPSYSPA01 → SYSTAC), pas du nom du fichier — celui-ci peut "
             "s'appeler n'importe quoi. Si le système n'est toujours pas reconnu, le "
             "fichier n'a probablement pas la colonne REFERENCE attendue, ou son "
             "contenu ne suit pas la codification RP[système][site][n°]. Le message "
             "d'erreur affiché montre un aperçu du contenu lu pour vous aider à "
             "diagnostiquer le problème."),
            ("Une cellule « RAS » ou vide dans la colonne Survenance, que devient-elle ?",
             "Elle est traitée comme un événement « non survenu », au même titre que "
             "« Non ». Seule la mention explicite « Oui » (quelle que soit la casse ou "
             "les espaces) compte comme un événement survenu."),
            ("Un événement du fichier n'a pas de code de référence, est-il perdu ?",
             "Non — DAN le conserve sous un identifiant généré (ex. HORS-REF-SYS-01) "
             "et reprend sa description depuis la colonne Motif si la colonne "
             "Événement est vide. Un avertissement s'affiche à l'import pour vous "
             "signaler ce cas. Ces événements sont comptés dans le score avec un "
             "niveau de risque par défaut, faute de correspondance possible avec le "
             "Référentiel de Surveillance."),
            ("La page Analyse des incidents liste-t-elle vraiment tous les incidents ?",
             "Oui — « Incidents survenus et causes probables » affiche l'intégralité des "
             "incidents survenus et de leurs motifs, pas seulement une sélection des "
             "plus urgents."),
            ("L'aperçu PDF ne s'affiche pas dans « Génération des rapports », pourquoi ?",
             "L'aperçu nécessite Microsoft Word ou LibreOffice installé sur cet "
             "ordinateur. Le fichier Word reste téléchargeable même sans aperçu."),
            ("Où sont stockées mes données ?",
             "Uniquement sur cet ordinateur, dans le dossier du projet DAN "
             "(data/, mapping/, outputs/) — rien n'est envoyé à l'extérieur."),
        ]
        for question, reponse in faq:
            with st.expander(question):
                st.write(reponse)

    with onglets[4]:
        st.subheader("Bonnes pratiques")
        st.markdown("""
- **Importez les fichiers du mois complet** avant de générer un rapport, pour
  que le score consolidé reflète bien tous les systèmes surveillés ce mois-ci.
- **Vérifiez le nombre de participants « Reçu »** (page Paramètres) après un
  import, et corrigez-le si l'estimation automatique ne correspond pas à la
  réalité — cette valeur alimente directement le rapport d'activité.
- **Consultez l'Historique régulièrement** pour suivre l'évolution du risque
  dans le temps plutôt que de ne regarder qu'un score isolé.
- **Sauvegardez votre configuration** (page Paramètres) après une modification
  importante, pour pouvoir la restaurer facilement.
        """)

    with onglets[5]:
        st.subheader("Contact")
        st.markdown(f"""
**Institution** : {config['nom_institution']}
**Direction** : {config['direction']}
**Responsable applicatif** : {config['responsable'] or "*(non renseigné — à définir en page Paramètres)*"}
        """)
        st.markdown("---")
        st.markdown("**Personne à contacter en cas de problème avec DAN**")
        st.markdown("""
- **Nom** : Tchomtchi Kamgang Daniel Merlys
- **E-mail** : tchomtchidaniel@gmail.com
        """)
        st.caption("ℹ️ Ce contact est fixe et ne se modifie pas depuis les Paramètres.")

    from pages_dan.widget_assistant import afficher_assistant
    afficher_assistant("Aide")
