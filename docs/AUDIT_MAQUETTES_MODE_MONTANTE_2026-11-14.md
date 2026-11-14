# Avis sur les maquettes « Mode Montante » MM1 à MM4 — 14 novembre 2026

Fichier relu : `docs/maquettes/8-mode-montante/` (maquettes du 14/11, à valider). Avis
fondé sur ce que j'ai vécu en jouant les montantes n° 7 et n° 8 du 9 au 13/11.

## Ce qui est bien

- Un seul interrupteur, et rien n'est supprimé : on revient à l'application complète.
- La mise imposée et la plage vérifiée dans « Palier » (MM4) évitent les erreurs de mise.
- « Si ça passe » et « Si j'arrête maintenant » sont affichés sur MM2.
- MM4 compare la chance du moteur à celle de la cote (« moteur 63 % · selon la cote 59 % »).

## Ce qui manque ou que je changerais

1. **L'état le plus fréquent n'est pas dessiné : « rien de valable aujourd'hui ».**
   - Du 9 au 13/11, mes montantes 7 et 8 n'ont eu **aucune** suggestion où le moteur battait
     la cote, sauf une fois, le 13/11 à 19:18.
   - En mode Montante, c'est donc l'écran que le joueur verra le plus souvent.
   - Il faut une maquette : « Aujourd'hui, aucun pari ne dépasse la cote dans ta plage.
     Attendre, c'est aussi jouer la montante. Prochaine vérification : … ».
   - Sans cet écran, le joueur va composer lui-même n'importe quoi pour « avancer ».
2. **Montrer aussi ce qu'on risque**, pas seulement ce qu'on gagne. Sur MM2 et MM4, ajouter
   « Si ça perd : −20 724 F, montante arrêtée ». La montante met tout en jeu à chaque palier,
   et le joueur doit le lire à côté du gain.
3. **MM4 : bloquer ou avertir quand le moteur est sous la cote.** L'exemple montre un cas
   favorable (63 % contre 59 %). Il faut dessiner le cas défavorable : bandeau ambre « Le
   moteur est moins confiant que la cote (55 % contre 59 %) », et le bouton devient
   « Jouer quand même ». C'est la même règle que les suggestions de montante.
4. **MM3 : aider à composer dans la plage.**
   - Mettre en évidence les cotes qui tombent dans la plage (1,65 à 1,75).
   - Afficher sous chaque cote la chance du moteur.
   - Montrer en bas, pendant la composition, la cote totale et « dans la plage ✓ / hors
     plage ».
   - Aujourd'hui, le joueur doit faire le calcul de tête.
5. **Les écrans manquants** :
   - aucune montante en cours : créer une montante (mise de départ, nombre de paliers,
     plage) ;
   - montante perdue, montante réussie, montante encaissée ;
   - palier en cours de jeu : suivi du match, chances en direct, « gagnant pour l'instant » ;
   - historique des montantes terminées.
6. **Quatre onglets, c'est peut-être un de trop.** « Palier » ne sert que pendant la
   composition. Il pourrait s'ouvrir comme une feuille depuis Montante ou depuis Matchs,
   comme « Mon coupon » aujourd'hui. Avec 3 onglets (Montante, Matchs, Profil), c'est plus
   simple.
7. **Le réglage devrait suivre le compte, pas le téléphone.** Le fondateur joue sur l'APK et
   sur le web : un réglage par appareil le surprendra (mode actif ici, pas là). Le réglage
   « Pendant mes matchs » est déjà enregistré sur le compte : faire pareil.
8. **Garder une fiabilité propre aux montantes.** La page Fiabilité est cachée, mais le
   joueur de montante doit pouvoir lire si les suggestions de palier tiennent leurs
   promesses : chance annoncée contre gagnée, paliers gagnés et perdus, bilan en argent. À
   placer dans « Voir l'analyse » (MM2).
9. **Notifications** : préciser qu'elles restent actives en mode Montante (rappel ⏰, « C'est
   parti », ⚽ du palier, palier validé ou perdu). Ce sont celles dont le joueur a le plus
   besoin.
10. **Exemple de MM2.** « Bilan des montantes +68 143 F » est un exemple flatteur. Montrer
    plutôt un bilan réaliste, ou neutre, pour ne pas donner l'idée que la montante rapporte
    à coup sûr. Ce point compte aussi pour les captures du Play Store.

## Rappel du terrain (13/11)

Ma montante n° 7 a joué sa seule suggestion valable (plus de 0,5 but en 1re mi-temps à 1,55,
moteur 69 % contre 65 %), et l'a perdue (0-0 à la pause). Une montante s'arrête au premier
palier perdu, même avec une suggestion favorable. Les écrans doivent le rendre visible,
sans faire peur, mais sans le cacher.
