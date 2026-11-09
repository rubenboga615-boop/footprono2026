# Recherche : obtenir les codes 1xBet automatiquement ? — 9 novembre 2026

Question du fondateur : peut-on obtenir les codes de réservation 1xBet (« booking code »)
automatiquement, au lieu de les saisir à la main dans la console ? Recherche sur internet
le 9/11 ; rien n'a été modifié dans le code.

## Ce que j'ai trouvé

- **Aucune API officielle de 1xBet** pour créer un code. Le code est créé sur le site ou
  dans l'application 1xBet (« Book a bet » / « Enregistrer le coupon ») à partir d'un coupon
  rempli à la main.
- **1xPartners** (programme d'affiliation de 1xBet) : liens de parrainage, codes promo et
  API de **statistiques** pour les affiliés ; rien de public sur la création de codes de
  coupon. À demander directement à un responsable d'affiliation.
- **Outils non officiels** (par exemple un « 1xBet Accumulator Builder » sur Apify) qui
  appellent les adresses internes du site 1xBet : non documentés, demandent un serveur
  dans un pays où 1xBet est autorisé, cassent dès que 1xBet change son site, et peuvent
  être contraires aux conditions de 1xBet (risque de blocage).
- Les API de cotes 1xBet (OddsPapi, SharpAPI…) donnent les cotes, pas les codes.

## Avis

1. **Ne pas automatiser par les adresses internes de 1xBet** : fragile et risqué pour la
   réputation de FootProba (blocage, conditions d'utilisation).
2. **Demander à 1xPartners** (s'inscrire comme affilié FootProba) si une création de code
   par API ou un lien « pré-rempli » existe pour les partenaires. C'est la seule voie
   propre ; en plus, l'affiliation peut rapporter une commission.
3. **En attendant** (peu d'utilisateurs) : ne pas promettre le code sur l'accueil ; afficher
   « Code disponible quand le fondateur l'a saisi » et, à la place, la liste des sélections
   à reproduire dans 1xBet (match, marché, choix, cote), avec un bouton « Copier ».
4. Quand il y aura des utilisateurs : saisir les 3 codes chaque matin reste réaliste
   (environ 5 minutes) ; la notification « codes prêts » existe déjà.

Sources : recherche web du 9/11/2026 (apify.com « 1xbet-accumulator-builder »,
sportingaz.com « generate a booking code on 1xbet », oddspapi.io, sharpapi.io,
statsdrone.com et affninja.com sur 1xPartners).
