# Nouveau logo FootProba — « Ballon-jauge » B3, validé par le fondateur le 13/11/2026

Un ballon rempli aux trois quarts, comme une chance de 75 % : le quart restant est en violet
clair, et le pentagone du centre est découpé (on voit le fond au travers). Couleurs de
`app/lib/theme.dart` : dégradé #8B6BFF → #5A36E6, dessin blanc.

| Fichier | Usage |
|---|---|
| `footproba-logo.svg`, `footproba-logo-1024.png` | icône complète (fond plein, sans coins arrondis), source pour toutes les tailles |
| `footproba-play-store-512.png` | icône Play Store 512 × 512 |
| `footproba-premier-plan.svg`, `-432.png` | Android, icône adaptative : premier plan transparent, dessin dans la zone sûre (66/108) |
| `footproba-fond.svg`, `-432.png` | Android, icône adaptative : fond (dégradé) |
| `footproba-notification.svg`, `-96.png` | petite icône des notifications Android : blanc sur transparent, quart restant à 30 % d'opacité, pentagone découpé |

À remplacer : icônes Android (mipmap, adaptative, notification `ic_stat_…` à brancher sur
Firebase), web (`web/icons/Icon-192`, `Icon-512`, `Icon-maskable-*`, `favicon.png`),
écran de démarrage, console (onglet), Play Store.

`pistes/` : les pistes comparées (A actuel, B à E) et les variantes de B, en situation.

## Correction du 13/11 (11 h) : icône Android trop grande

Sur le téléphone du fondateur (capture `capture-telephone-fondateur-13-11.jpg`), le ballon
remplit presque toute l'icône, sans marge, à la différence des autres applications. **Mon
erreur** : dans `footproba-premier-plan.svg`, le ballon fait 66 sur 108, toute la zone sûre.
Or le lanceur ne montre que les 72 du centre, et le ballon en occupe donc 92 %.

**Remplacer par `footproba-premier-plan-v2.svg` / `-v2-432.png`.** Le ballon y fait 52 sur
108, soit environ 72 % de la partie visible, comme les autres icônes. Le quart restant passe
de 30 à 40 % d'opacité, pour qu'il se voie mieux sur le fond violet. Avant / après :
`avant-apres-android.png`.

Les icônes web, la console et l'icône complète 1024 ne changent pas : elles ont déjà la
bonne marge.
