# Console d'administration : export de l'Observatoire bêta — 7 novembre 2026

Signalé par le fondateur (capture d'écran du téléphone, 03 h 47) ; analyse du code de la
console, sans accès administrateur de mon côté. Rien n'a été modifié.

## Ce que le fondateur a fait et vu

Console → Observatoire bêta → onglet **Bêta** → « **Exporter (sans données
personnelles)** ». Deux messages en même temps en bas de l'écran :
- message de la console : « **Export téléchargé** : numéros de testeur seulement, ni nom ni
  téléphone. » ;
- message d'Android : « **Aucune application pour ouvrir ce lien** ».

Aucun fichier n'est arrivé dans le téléphone.

## Cause (code)

`backend/src/footprono/web/admin/admin.js`, fonction `exportBeta` : les données sont
lues par `GET /admin/console/beta/export`, puis transformées **dans la page** en
`Blob`, et un lien `blob:` avec l'attribut `download` est « cliqué » par le script.

- Dans Chrome, cela enregistre un fichier. Mais la console ouverte **depuis l'icône de
  l'écran d'accueil** (application installée, d'après le badge FootProba du message
  Android) ne sait pas enregistrer un lien `blob:` : Android cherche une autre
  application pour l'ouvrir et n'en trouve pas.
- Le message « Export téléchargé » est affiché **juste après le clic, sans savoir si le
  fichier a été enregistré** : il annonce un succès qui n'a pas eu lieu.

## Contournement immédiat

Ouvrir la console dans **Chrome** (adresse tapée, pas l'icône de l'écran d'accueil),
puis « Exporter ».

## Pistes pour le développement

1. Sur téléphone, proposer le fichier avec **le partage d'Android** (`navigator.share`
   avec un fichier JSON) : « Enregistrer dans Fichiers », WhatsApp, Gmail…
2. Ou télécharger un vrai fichier depuis le serveur (réponse avec
   `Content-Disposition: attachment`, par exemple via un lien à usage unique créé par la
   console), que toutes les applications savent enregistrer.
3. En secours, un bouton « **Copier** » (presse-papiers) à côté de « Exporter ».
4. Ne plus afficher « Export téléchargé » : écrire « Fichier prêt » seulement quand le
   partage ou le téléchargement a réellement démarré.

## Remarque sur les chiffres affichés

L'écran Bêta montre « Rendement global **+79 %** » et « Réussite 60 % » pour **1 testeur
et 15 paris réglés**. Sur si peu de paris, un ou deux gains à grosse cote suffisent : le
chiffre n'est pas significatif. **Piste** : comme la page Fiabilité, afficher « trop peu
de paris pour conclure » sous un seuil (par exemple 200 paris), pour ne pas tirer de
conclusion, ni la reprendre dans une communication.

## Vérification : export réussi dans Chrome (04 h 00)

Le fondateur a ouvert `https://footproba.duckdns.org/admin/` dans Chrome et l'export a
fonctionné (`footproba-observatoire-2026-11-07.json`, exporté à 04:00:19 GMT). Le défaut
ne concerne donc que la console ouverte depuis l'icône de l'écran d'accueil.

## Lecture de l'export

| Donnée | Valeur | Commentaire |
|---|---|---|
| Testeurs volontaires | 1 | |
| Paris réglés | 15 ; réussite 60 % ; rendement **+78,85 %** | trop peu pour conclure (voir plus haut) |
| Montantes | 6 ; meilleur palier atteint : 3 | `montantes_lost_at_step` vide : aucune montante perdue enregistrée, alors qu'aucune n'a dépassé le palier 3 (à vérifier : montantes encore en cours ou arrêtées ?) |
| Coupons intelligents | `composed: 0`, `added: 0` | à vérifier : le testeur ne s'en est-il jamais servi depuis le début de la collecte, ou ces actions ne sont-elles pas enregistrées ? |
| Écrans mesurés | « Bookmaker » seulement (3 requêtes `/bets`, 1,05 à 1,25 s) | aucun autre écran mesuré : la collecte ne couvre peut-être que quelques écrans |
| Événements | 3 ; **deux ont exactement la même heure** (03:41:27.900405) | l'heure semble être celle de l'envoi groupé au serveur, pas celle de l'action : l'ordre réel des actions est perdu |

**Sélections du testeur** (69, tous marchés) : annoncé **74,1 %**, arrivé **85,5 %**, soit
+11 points, environ deux fois la marge du hasard (5,3 points). Même sens que la
calibration réelle du moteur vue sur la page Fiabilité (le moteur est trop prudent sur
les favoris). Mais 69 sélections d'un seul joueur, dont plusieurs dans les mêmes paris,
ne prouvent rien à elles seules.

Par marché, aucun n'a assez de sélections pour conclure (de 1 à 23). À noter :
« Double chance » 7 sélections, annoncé 66 %, arrivé **43 %** ; « **DNB** » n'est pas
traduit (« Remboursé si nul »).

**Pistes** : horodater chaque événement au moment de l'action sur le téléphone ;
mesurer aussi les écrans Coupon intelligent, Matchs, Match et Montante ; traduire « DNB ».
