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

## Correction du 13/11 (11 h 30) : ballon réduit au cercle orange du fondateur

Sur le téléphone du fondateur (`capture-telephone-fondateur-13-11.jpg`), le ballon
remplissait presque toute l'icône Android (66 sur 108, alors que le lanceur n'en montre que
les 72 du centre).

**Demande du fondateur** (`demande-fondateur-cercle-orange.png`) : réduire le rayon du
ballon jusqu'au cercle orange, **en gardant le pentagone à sa taille**. Le ballon occupe
donc **74 % de la partie visible de l'icône**, avec un pentagone de rayon 0,50 × celui du
ballon (au lieu de 0,41). C'est la même règle sur tous les supports (aperçu :
`apercu.png`). Le quart restant est à 40 % d'opacité.

| Fichier | Partie visible | Ballon |
|---|---|---|
| `footproba-logo.svg` / `-1024.png`, `footproba-play-store-512.png`, `web/Icon-192.png`, `web/Icon-512.png`, `web/favicon.png` | toute l'icône | 74 % du côté |
| `footproba-maskable.svg`, `web/Icon-maskable-192.png`, `-512.png` | cercle de 80 % | 74 % de 80 % |
| `footproba-premier-plan.svg` / `-432.png` (Android adaptatif, et `monochrome`) | 72 sur 108 | 74 % de 72 |
| `footproba-fond.svg` / `-432.png` | — | dégradé |
| `footproba-notification.svg` / `-96.png` | petite icône des notifications | remplit l'icône (normal) |

Fichiers prêts à copier tels quels : `web/` → `app/web/`.
