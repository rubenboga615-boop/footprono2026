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
