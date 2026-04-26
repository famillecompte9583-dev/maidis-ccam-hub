# Maidis CCAM Hub — déploiement public et local

## Objectif du site
Annuaire statique d’aide à la recherche CCAM, au contrôle de tarifs et au paramétrage métier. Le site est pensé pour un usage public : il doit rester lisible, traçable, prudent sur les données de santé/facturation et robuste même si une source distante échoue.

## Ce que contient le site
- Site multi-page statique : `index.html`, `actes.html`, `acte.html`, `dossiers.html`, `article.html`, `changements.html`, `guides.html`, `exports.html`, `actualites.html`.
- Base embarquée : `data/app-data.js` et `data/app-data.json`.
- Statut de diagnostic : `data/sync-status.json`.
- Reconstruction CCAM : `scripts/update_all.py`.
- Enrichissement éditorial Ameli : `scripts/enrich_articles.py`.
- Relecture IA optionnelle : `scripts/ai_review_articles.py`.
- Validation avant publication : `scripts/validate_public_data.py`.
- Workflow GitHub Action : `.github/workflows/update-all.yml`.
- Petit serveur local optionnel : `server.py`.

## Pourquoi ça fonctionne en local
La base est chargée depuis un fichier JavaScript embarqué (`data/app-data.js`). Le navigateur n'a pas besoin d'appeler directement les flux, PDF ou API distantes. Cela évite les blocages CORS, permet un usage local et rend le site hébergeable simplement via GitHub Pages.

## Mode local recommandé
```bash
python server.py
```
Puis ouvrir : http://localhost:8000

Pour reconstruire la base depuis Internet :
```bash
python server.py --update
```

Pour contrôler la publication :
```bash
python scripts/validate_public_data.py
```

## Hébergement permanent recommandé : GitHub Pages
1. Créer ou utiliser le dépôt GitHub `maidis-ccam-hub`.
2. Aller dans **Settings > Pages**.
3. Source : `Deploy from a branch`, branche `main`, dossier `/root`.
4. Le workflow `.github/workflows/update-all.yml` reconstruit la base, génère les dossiers, exécute la relecture IA si une clé est disponible, puis valide avant commit.

## Relecture Gemini optionnelle
Le site peut utiliser Gemini comme relecteur éditorial contrôlé des dossiers générés automatiquement. Gemini ne remplace pas les sources officielles : il améliore uniquement la clarté, la structure et la mise en page des articles déjà extraits.

Pour l’activer dans GitHub :
1. Aller dans **Settings > Secrets and variables > Actions**.
2. Créer un secret nommé `GEMINI_API_KEY`.
3. Coller la clé API Google AI Studio dans ce secret.
4. Lancer le workflow manuellement ou attendre le prochain passage planifié.

Paramètres utiles :
- `GEMINI_MODEL` : modèle utilisé, par défaut `gemini-2.5-flash-lite`.
- `AI_REVIEW_MAX_ARTICLES` : nombre maximum d’articles relus par passage, par défaut `12`.

Si `GEMINI_API_KEY` est absente, l’étape IA est simplement ignorée et le site continue avec le générateur local.

## Politique de mise à jour
La donnée institutionnelle ne nécessite pas un scraping toutes les 5 ou 15 minutes. La cadence recommandée est de deux passages quotidiens, plus un lancement manuel via `workflow_dispatch` en cas de besoin urgent. Cette approche évite les commits artificiels, réduit la charge sur les sources et rend les changements réellement lisibles.

## Sources suivies
- Base CCAM Healthref/OpenDataSoft avec plusieurs URLs de repli.
- Pages Ameli ciblées : CCAM, convention dentaire, calendrier conventionnel, tarifs, 100 % Santé.
- PDF institutionnels liés aux pages suivies lorsqu’ils sont accessibles.

## Garde-fous publics
- Le site conserve la dernière base valide si les sources fraîches échouent.
- La validation bloque une publication si la base est vide ou trop faible, si les métadonnées sont incohérentes, si des URLs sont invalides ou si un article contient du HTML dangereux.
- Les rendus JavaScript échappent les champs injectés dans les tableaux, fiches, actualités et changements.
- Les dossiers générés sont des synthèses pratiques, pas des copies intégrales des sources.
- La relecture IA est filtrée : HTML autorisé limité, URLs contrôlées, codes CCAM limités aux codes déjà détectés ou présents dans la base.

## Intégration Maidis
Le site ne se connecte pas directement à Maidis car le format d'import dépend de votre version et de votre paramétrage. La page **Exports** produit un CSV neutre contenant : code CCAM, activité, phase, libellé, BRSS, taux, montant AMO estimé, panier, domaine et notes.

## Avertissement métier
Les taux et montants AMO affichés sont des aides au paramétrage. Les cas ALD, AT/MP, maternité, C2S, Alsace-Moselle, DOM, modificateurs, associations d'actes et rejets CPAM doivent être validés avec les textes officiels, les règles opposables et votre logiciel métier.
