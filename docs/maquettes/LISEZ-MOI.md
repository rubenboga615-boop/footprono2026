# Maquettes de la nouvelle interface FootProba

Validées par le fondateur le 7 novembre 2026. À reproduire dans l'application Flutter
(`app/`), écran par écran.

## Ordre de lecture

1. **`1-validees/`** : les maquettes validées par le fondateur (style de référence :
   fond `#0E0B1A`, cartes `#1A1530`, violet `#6D4AFF` / `#7C5CFF`, texte secondaire
   `#A9A3C2`, vert `#4ADE80`, rose `#FF8A9B`, ambre `#E7C98A`, police Inter).
   `Maquettes-Liste-des-matchs-source.html` est le fichier d'origine (à ouvrir dans Chrome).
   La liste des matchs retenue est **E-ecran-complet-matchs** (cartes, heure au centre).
2. **`2-corrigees/`** : **priorité sur `1-validees/`** quand un écran existe dans les deux.
   - `C1` à `C9` remplacent : liste des matchs (E), montante (H), coupon (G), résultat du
     Coupon intelligent (Z2), fiabilité (T), profil (M/AE), pari en cours (X), Wave (Q),
     Passer Premium (P).
   - `N1` à `N16` : écrans qui manquaient (écrans verrouillés du compte gratuit,
     confirmation du pari, match commencé, montante, mouvements, historique de cote,
     arbitre, mot de passe oublié, « Presque prêt », états chargement / vide / erreur).
   - `index.html` : tous les écrans côte à côte, avec ce qui change.
3. **`3-application-actuelle/`** : captures de l'application du 7/11 (version web de
   15 h 17), rangées par partie, pour savoir d'où l'on part et ne rien oublier.

## Règles

- Les **textes et les règles de l'application actuelle restent valables** (messages
  honnêtes, « argent fictif », « pas un conseil de pari », chances réelles) : la maquette
  change la présentation, pas ce qui est dit.
- Les chiffres des maquettes sont des **exemples** : brancher les vraies données.
- Avis détaillé et raisons de chaque correction : `docs/AUDIT_MAQUETTES_2026-11-07.md`.
