# Design de l'application

**Direction retenue (30/09/2026) : A — « Verre violet ».** Maquettes :
https://claude.ai/artifact/YDQWBaNN1Kp6JZrYwyeFvW (directions B « verre rouge » et
C « tableau de bord néon » conservées pour mémoire ; C pourra servir à la
version web et à l'administration).

## Principes visuels

- Fond très sombre (`#060509`) animé de reflets lumineux dans la couleur d'accent.
- Cartes en verre : fond `rgba(18,16,26,0.72)`, flou d'arrière-plan 18 px,
  bordure claire en dégradé, **coins supérieur gauche et inférieur droit coupés**
  (30 px pour les cartes principales, 16-18 px pour les cartes de liste),
  petits triangles décoratifs aux coins des cartes principales.
- Titres en deux tons : premier mot blanc, second dans l'accent clair
  (« Bon **retour** », « Matchs **du jour** »).

## Couleurs

| Rôle | Valeur |
|---|---|
| Accent (boutons, sélection) | `#7C3AED`, texte blanc |
| Accent clair (texte sur fond sombre) | accent mélangé à 45 % de blanc |
| Texte principal | `#F4F2F8` |
| Texte secondaire | `#F4F2F8` à 68 % d'opacité |
| Gagné | `#34D399` |
| Perdu | `#F472B6` (jamais la couleur d'accent) |

## Typographie

- Titres et chiffres : **Sora** 600-700.
- Texte : **Plus Jakarta Sans** 400-700.

## Règles produit visibles dans les maquettes

- Les probabilités affichées viennent du moteur ; tant qu'il n'existe pas,
  aucune valeur n'est inventée dans l'application (les maquettes utilisent des
  valeurs d'exemple, signalées).
- Le bookmaker virtuel est présenté comme de l'argent fictif.
- Inscription : case « 18 ans ou plus » ; profil : entrée « Jeu responsable ».
- Page publique « Fiabilité du modèle » : probabilité annoncée contre fréquence
  observée, par marché.
- Paiement de l'abonnement : Mobile Money.

## Écrans maquettés

Connexion, Inscription, Matchs du jour, Détail du match (probabilités),
Analyse du match (forme, points clés, moyennes, confrontations, compositions),
Coupon, Montante, Bookmaker virtuel, Fiabilité du modèle, Notifications,
Profil et abonnement.
