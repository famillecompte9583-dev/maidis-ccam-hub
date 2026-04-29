# Annuaire CCAM Santé

Site statique public d’aide à la consultation CCAM, au contrôle de tarifs de base, à la lecture des paniers 100 % Santé et à la préparation d’exports de travail pour un usage métier prudent.

## Objectif
Le dépôt publie un site autonome qui :
- synchronise une base CCAM depuis des sources publiques robustes ;
- enrichit le contenu avec des dossiers et sources techniques publiques ;
- valide les données avant publication ;
- reste consultable en local ou via GitHub Pages.

Le projet ne remplace ni les textes officiels, ni les règles opposables, ni la validation métier dans Maidis ou dans tout autre logiciel.

## Stack
- Front statique : HTML, CSS, JavaScript vanilla
- Pipeline : Python 3.11
- Hébergement : GitHub Pages
- Automatisation : GitHub Actions

## Arborescence utile
- `index.html`, `actes.html`, `acte.html`, `dossiers.html`, `article.html`, `sources.html`, `actualites.html`, `changements.html`, `guides.html`, `exports.html` : pages publiques
- `js/` : logique front
- `data/` : données publiées embarquées dans le site
- `scripts/` : synchronisation, enrichissement, validation
- `.github/workflows/` : CI et automatisation
- `tests/` : tests unitaires et de non-régression légère

## Lancement local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Puis ouvrir : http://localhost:8000

Pour reconstruire la base avant de servir le site :
```bash
python server.py --update
```

Pour choisir un port personnalisé :
```bash
python server.py --port 8080
```

## Vérification locale
```bash
pytest -q
python scripts/validate_public_data.py
```

## Workflow de publication
Le workflow `update-all.yml` :
1. installe les dépendances ;
2. exécute les tests ;
3. synchronise la base CCAM ;
4. enrichit les dossiers et les sources publiques ;
5. applique la relecture IA si une clé est disponible ;
6. valide les données ;
7. commit automatiquement les fichiers de données si un changement publiable est détecté.

## Déploiement
Le guide détaillé reste dans `README_DEPLOIEMENT.md`.

## Principes de qualité
- ne pas publier une base vide à la place d’une base valide ;
- échapper les contenus injectés côté front ;
- bloquer le HTML dangereux et les pages anti-bot publiées par erreur ;
- conserver un site utile même si certaines sources externes échouent ;
- séparer les dossiers d’actualité des sources/API publiques.

## Limites connues
- certaines sources institutionnelles peuvent être protégées contre les robots ;
- la relecture IA reste optionnelle et dépend des quotas du fournisseur ;
- les montants et taux affichés sont des aides à la lecture, pas des décisions opposables.
