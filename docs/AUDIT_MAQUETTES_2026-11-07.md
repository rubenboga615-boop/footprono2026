# Avis sur les maquettes de toute l'application — 7 novembre 2026

Fichier reçu du fondateur : « Maquettes – Liste des matchs » (40 maquettes, de A à AI).
Les variantes A, B et C ne s'affichent pas dans le fichier (cadres vides) ; D/E est la
maquette validée. Rien n'a été modifié dans le code.

## Verdict

Très bon travail : un style unique sur les 40 écrans (fond sombre, violet, cartes
arrondies), plus lisible que l'application actuelle, et **les messages honnêtes sont
conservés** (« Calculées avant le coup d'envoi… Paris fermés », cotes « fermé », « On ne
promet pas de gains », chance du coupon 86 % × 86 % × 86 % = 64 %). Les corrections
récentes y sont : « Tout effacer » et glisser pour effacer les notifications, « 0 sur 3
validée · 1 en cours · 2 à venir », coches ✓/✗ par sélection, « Retirer sans remplacer ».

## À corriger avant de les confier au développement

| # | Écran | Constat | Piste |
|---|---|---|---|
| 1 | **Liste des matchs** (D, E) | grandes cartes : environ **3 matchs par écran** (11 aujourd'hui) ; un samedi a plus de 60 matchs | garder les cartes mais plus basses (logos et noms sur une ligne), ou regrouper par championnat repliable |
| 2 | Liste des matchs | **plus de cotes** sous les 1 / N / 2 (le fondateur les avait demandées) ; légende de l'encadré absente ; puce « Tous cham… » coupée | cote en petit sous chaque % ; une ligne « encadré : l'issue la plus probable » ; puce plus courte (« Championnats ▾ ») |
| 3 | **Montante** (H) | la **chance d'aller au bout** (≈ 4 sur 100) n'apparaît pas ; rien n'explique la montante | à côté de l'objectif ; une phrase d'explication |
| 4 | **Mon coupon** (G) | on ne voit ni la **mise**, ni « Tu récupères », ni la chance du moteur, ni l'alerte « coupon risqué », ni « Placer le pari » | ajouter le bas d'écran actuel, dans le nouveau style |
| 5 | **Coupon intelligent, résultat** (Z2) | la **chance du coupon (2,8 %)** n'est pas à côté de la cote 31,32 ; « moteur 60 % » répété partout | « 31,32 · environ 3 chances sur 100 » en haut |
| 6 | **Fiabilité** (T) | onglet « Simulation » affiché en premier ; le verdict réel « **pas encore juste** : annoncé 44 % → arrivé 58 % » n'est pas visible | ouvrir sur « Depuis le lancement », verdict en bandeau |
| 7 | **Profil** (M, AE) | pas de « **Se déconnecter** », ni « Conditions d'utilisation », ni l'interrupteur « Aider à améliorer FootProba » | les remettre en bas |
| 8 | **Pari en cours** (X) | « en cours 20' » : pas de « Mi-temps », ni « gagnante pour l'instant » | libellé identique à la liste ; point vert / rouge selon le score |
| 9 | Wave (Q) | numéro masqué « +225 XX XX… » | vrai numéro +225 05 00 64 99 04 (« le même que l'aide WhatsApp ») |
| 10 | Passer Premium (P) | tableau de 3 lignes seulement | toutes les lignes du tableau actuel (Coupon intelligent, analyse, montante…) |

## Écrans qui manquent dans les maquettes

- **Écrans verrouillés du compte gratuit** (les plus importants pour vendre Premium) :
  Coupon intelligent verrouillé avec l'exemple flouté, Analyse verrouillée, Coupons du jour
  sans les sélections, Profil gratuit avec le tableau Gratuit / Premium.
- Coupon : saisie de la **mise**, confirmation « Placer le pari », message « match commencé ».
- Montante : création (mise de départ, plan des paliers) et suggestions du moteur.
- Mes paris : onglet **Mouvements** ; Mon bilan suite.
- Match : historique d'une cote, fiche de l'arbitre, onglet Analyse d'un match en direct.
- Mot de passe oublié ; écran Google « Presque prêt » (pays, 18 ans).
- **États** : chargement (cotes « … »), liste vide (aucun match ce jour), erreur réseau.

## Lisibilité

Plusieurs textes gris très petits (sous-titres, « moteur 60 % », dates) sur fond violet
foncé : à vérifier sur un vrai téléphone en plein soleil (contraste et taille d'au moins
12 points).

## Suite : maquettes corrigées (envoyées au fondateur, 16 h 57)

À la demande du fondateur, les corrections ci-dessus ont été dessinées dans le même style
(fichier `FootProba-maquettes-corrigees.zip`, transmis hors du dépôt) : **C1 à C9**
remplacent les maquettes corrigées (liste des matchs, montante, coupon, résultat du Coupon
intelligent, fiabilité, profil, pari en cours, Wave, Passer Premium) ; **N1 à N16** sont les
écrans qui manquaient (écrans verrouillés du compte gratuit, confirmation du pari, match
commencé, création et suggestions de montante, mouvements, historique de cote, arbitre,
mot de passe oublié, « Presque prêt », chargement, aucun match, erreur réseau).
Les chiffres de ces maquettes sont des exemples.
