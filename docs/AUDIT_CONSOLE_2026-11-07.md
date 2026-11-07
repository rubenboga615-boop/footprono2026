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
