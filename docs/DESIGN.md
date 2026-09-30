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

## Pays et devise (décidé le 30/09/2026)

- Lancement en **Afrique de l'Ouest** ; devise par défaut **franc CFA (XOF)**,
  affiché « F CFA », sans centimes, espace insécable entre les milliers
  (`150 582 F CFA`).
- Pays choisi à l'inscription (Bénin, Burkina Faso, Côte d'Ivoire,
  Guinée-Bissau, Mali, Niger, Sénégal, Togo au lancement) : il fixe la devise
  des montants, du bookmaker virtuel et du prix de l'abonnement. D'autres
  devises (XAF, etc.) pourront être ajoutées ; côté serveur, les montants sont
  stockés en entiers dans l'unité de la devise avec son code ISO 4217.

## Montante (validée le 30/09/2026)

1. Tableau par palier : mise, cote, gain ; gain final mis en avant.
2. **Mise de départ libre** (5 000 F CFA par défaut, raccourcis 1 000 / 5 000 /
   10 000 / 25 000) et nombre de paliers réglable (4 à 8).
3. **Plage de cotes par palier** (par exemple 1,55 – 1,65) au lieu d'une cote
   imposée : tout pari dans la plage convient ; hors plage, l'application
   prévient. Les gains se calculent avec la cote réellement jouée ; pour les
   paliers à venir, mise et gain sont affichés en fourchette (minimum – maximum).
4. Probabilités honnêtes : probabilité du modèle pour chaque pari, chance
   cumulée d'aller au bout selon le modèle **et** selon les cotes, somme
   encaissable à tout moment.
5. « Encaisser » à n'importe quel palier ; option « sécuriser X % de chaque gain ».
6. Calcul exact au franc près (arrondi inférieur, comme un bookmaker).

Exemple de référence (6 paliers, départ 5 000 F CFA, cotes 1,60 → 1,90) :
gain final exact 150 582 F CFA ; chance d'aller au bout selon les cotes 3,3 %
avant marge du bookmaker (environ 2,5 % avec une marge de 5 % par pari).

## Écrans maquettés

Connexion, Inscription, Matchs du jour, Détail du match (probabilités),
Analyse du match (forme, points clés, moyennes, confrontations, compositions),
Coupon, Montante (écran défilant), Bookmaker virtuel, Fiabilité du modèle, Notifications,
Profil et abonnement.
