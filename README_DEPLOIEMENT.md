# Maidis CCAM Hub — déploiement permanent et local

## Ce que contient le site
- Site multi-page statique : `index.html`, `actes.html`, `acte.html`, `guides.html`, `exports.html`, `actualites.html`.
- Base embarquée : `data/app-data.js` et `data/app-data.json`.
- Script de reconstruction : `scripts/update_all.py`.
- Workflow GitHub Action : `.github/workflows/update-all.yml`.
- Petit serveur local optionnel : `server.py`.

## Pourquoi ça fonctionne en local
La base est chargée depuis un fichier JavaScript embarqué (`data/app-data.js`). Le navigateur n'a pas besoin d'aller appeler directement les flux RSS ou les API distantes. Cela évite les blocages CORS et permet d'ouvrir le site sur des postes internes.

## Mode local recommandé
```bash
python server.py
```
Puis ouvrir : http://localhost:8000

Pour reconstruire la base depuis Internet :
```bash
python server.py --update
```

## Hébergement permanent recommandé : GitHub Pages
1. Créer un dépôt GitHub, par exemple `maidis-ccam-hub`.
2. Copier tout le contenu de ce dossier dans le dépôt.
3. Aller dans **Settings > Pages**.
4. Source : `Deploy from a branch`, branche `main`, dossier `/root`.
5. Le workflow `.github/workflows/update-all.yml` reconstruira automatiquement la base et la veille.

## Intégration Maidis
Le site ne se connecte pas directement à Maidis car le format d'import dépend de votre version et de votre paramétrage. La page **Exports Maidis** produit un CSV neutre contenant : code CCAM, activité, phase, libellé, BRSS, taux, montant AMO estimé, panier, domaine et notes.

## Avertissement métier
Les taux et montants AMO affichés sont des aides au paramétrage. Les cas ALD, AT/MP, maternité, C2S, Alsace-Moselle, DOM, modificateurs, associations d'actes et rejets CPAM doivent être validés avec les textes officiels et votre logiciel métier.
