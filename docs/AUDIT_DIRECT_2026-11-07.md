# Matchs en direct : essai réel — 7 novembre 2026, 13 h 35 GMT

Serveur `86e4679`, version web du 07/11 à 10:43. Compte Premium **+225 07 84 89 71 95**,
téléphone émulé (Pixel 7), pendant les matchs de 13 h (Liga, Süper Lig, Roumanie, Israël),
Leeds – Tottenham (mi-temps) et Zemun – IMT Novi Beograd (78e). Rien n'a été modifié dans
le code.

## 1. Liste des matchs : les matchs en cours apparaissent deux fois

| Ce que j'ai vu | Commentaire |
|---|---|
| Section « **En direct** » en haut : « 76' Zemun 1 - 0 IMT Novi B… », « MT Leeds 0 - 0 Tottenham », « 33' Malaga 1 - 0 Racing Sa… »… avec « — » à la place des % et les cotes d'avant-match (5,52 · 4,04 · 1,60) | |
| Puis section « Samedi 7 novembre » : **les mêmes 6 matchs une deuxième fois**, cette fois avec les % d'avant-match (10 % · 22 % · 68 %) et les mêmes cotes | doublon signalé par le fondateur, confirmé |

**Pistes** : un match en cours n'apparaît que dans « En direct » ; dans cette section,
pas de cotes d'avant-match (elles ne sont plus jouables, voir 3) mais le score et la minute.

## 2. Écran d'un match en cours : tout est resté « avant le match »

Zemun – IMT Novi Beograd, **1-0 à la 78e** :
- en-tête correct : « 1 - 0 · En direct 78' » ;
- « Les choix du moteur » : « Sûr : Zemun encaisse au moins un but, 86 %, 1,20 »,
  « Équilibré : plus de 1,5 but, 75 %, 1,24 »… : chances et cotes **d'avant le match** ;
- « Résultat du match : Zemun 10 % · Nul 22 % · IMT 68 % » et « **score le plus probable :
  0-2** », alors que Zemun mène 1-0 à la 78e.

Le joueur lit des chances qui ne correspondent plus du tout au match. **Piste immédiate** :
pendant le match, masquer ces chances (ou les marquer « avant le match ») jusqu'aux
« chances en direct » (`AUDIT_PROPOSITION_DIRECT_2026-11-07.md`, étape 1).

## 3. On peut ajouter au coupon la cote d'un match déjà commencé

| Action | Résultat |
|---|---|
| Match en cours (78e) → toucher « 1,20 Bet365 » | « **Ajouté au coupon** » |
| Coupon → « Placer le pari » | refus : « **match 106064 déjà commencé : paris fermés** » (400) |

Le serveur protège bien (aucun pari possible), mais l'application laisse ajouter, puis
affiche un message technique avec un numéro interne. **Pistes** : désactiver les cotes d'un
match commencé (« Match commencé ») ; message « Leeds – Tottenham a commencé : retire-le
du coupon » ; retirer automatiquement du coupon les matchs commencés.

## 4. Temps additionnel et prolongation non pris en compte

`ingestion/live.py` garde seulement `fixture.status.elapsed` dans `live_minute` ;
le champ `fixture.status.extra` (minutes de temps additionnel) n'est lu nulle part
(ni serveur ni application). À 90+4, l'application affiche « 90' ». Les statuts sont bien
reconnus (« MT » pour la mi-temps ; `ET`, `BT`, `P` pour la prolongation et les tirs au but
dans `LIVE_STATUSES`), mais l'affichage ne dit pas « Prolongation » ni « Tirs au but ».
**Pistes** : afficher « 45+2' », « 90+4' » ; « Prol. 105' », « Tirs au but » ; pour les paris,
rappeler que seul le temps réglementaire compte (déjà le cas dans `regulation_score`).

## 5. Statistiques en direct : sans requête de plus (correction de ma proposition)

Le fondateur a raison. Le suivi en direct appelle déjà `/fixtures?ids=` (20 matchs par
requête, toutes les 2 minutes) et lit dans cette réponse les compositions (`lineups`).
D'après la documentation d'API-Football, la même réponse contient aussi **les événements
(`events` : buts, cartons, remplacements à la minute) et les statistiques (`statistics` :
tirs, tirs cadrés, possession, corners, cartons)** de chaque match. Elles sont aujourd'hui
ignorées. Seul le découpage par mi-temps demande `/fixtures/statistics?half=true`.

**Correction** : mon estimation de « 7 200 requêtes un samedi » (proposition du 7/11,
étape 2) est fausse : les statistiques en direct ne coûtent **aucune requête de plus**. À
vérifier sur une réponse réelle archivée (`raw_files`, source API-Football, suivi en
direct) avant de s'appuyer dessus.

## 6. Coupons sur des matchs en direct : avis

- **Techniquement** : avec l'étape 1 (chances en direct à partir du score et de la minute)
  et les statistiques déjà reçues, l'application peut montrer des chances à jour. Mais pour
  **proposer** un coupon, il faut une **cote en direct réelle** : aujourd'hui, seules les
  cotes d'avant-match sont relevées, et elles ne sont plus jouables (voir 3). Sans cote en
  direct, aucun coupon en direct possible (règle : aucune cote inventée).
- **Fiabilité** : les chances en direct doivent être vérifiées sur des matchs passés avant
  d'être publiées, comme les autres marchés.
- **Jeu responsable** : pas de nom « rattrapage », jamais proposé juste après une perte,
  limité (par exemple un coupon en direct par heure).
- **Ordre conseillé** : corriger 1 à 4 ; afficher les statistiques et événements déjà reçus
  (onglet « En direct ») ; chances en direct ; puis seulement, si des cotes en direct sont
  disponibles (`/odds/live`), le coupon en direct.

## 7. Pari de test placé pour suivre le direct

Coupon intelligent Sûr, Aujourd'hui : **pari n° 32**, cote 1,556, mise 1 000 F :
Maccabi Haifa – Maccabi Netanya (15:30, Netanya −3), Hapoel Katamon – Bnei Sakhnin (16:00,
buts de Katamon moins de 2,5), Antwerp – Lommel (19:45, moins de 4,5 buts). À suivre :
avancement « x sur 3 validées », minute, temps additionnel, règlement de chaque sélection.

## 8. Autres remarques

- Les cotes de la liste arrivent toujours en **10,6 s** (`/offers/main`).
- Libellé contradictoire : « **Sans encaisser de but** · Zemun encaisse au moins un but »
  (titre du marché « clean sheet » et sélection « non »). **Piste** : « Zemun encaisse au
  moins un but » seul, ou « Clean sheet Zemun : non ».

## 9. Suivi du pari n° 32 — 16 h 20 GMT (serveur `45039a7`, version web de 15 h 17)

Maccabi Haifa – Maccabi Netanya à la **mi-temps (0-0)**, Hapoel Katamon – Bnei Sakhnin à la
**19e (0-0)**, Antwerp – Lommel à venir (19:45).

| Point (essai de 13 h 35) | Constat de 16 h 20 |
|---|---|
| §1 Doublon dans la liste | **corrigé** : chaque match en cours n'apparaît qu'une fois, dans « En direct » (« MT Maccabi Haifa 0 - 0 Maccabi Netanya », « 19' Hapoel Katamon 0 - 0 Bnei Sakhnin ») |
| §2 Chances d'avant-match pendant le direct | **corrigé** : bandeau « Chances calculées avant le coup d'envoi : elles ne tiennent pas compte du score. Score actuel : 0 - 0 (MT). Paris fermés sur ce match. » ; plus de « choix du moteur » |
| §3 Cotes d'un match commencé ajoutables | **corrigé** : chaque cote est marquée « fermé » |
| §4 Temps additionnel | **corrigé** dans la liste (« 90+1' » vu à 15 h 58 pour HNK Gorica – Slaven Belupo ; « 45+3' » sur la capture du fondateur) ; en-tête du match : « 0 - 0 Mi-temps », « En direct 19' » |
| Fiche du pari 32 | « **0 sur 3 validée · 2 en cours · 1 à venir** », chaque sélection avec son état : « en cours 19' · 0-0 », « à venir » |

**Nouveaux petits constats** :
1. **Fiche du pari : « en cours 45' » pendant la mi-temps** de Maccabi Haifa – Netanya, alors
   que la liste et l'écran du match disent « MT » / « Mi-temps ». **Piste** : même libellé
   partout (« Mi-temps · 0-0 »).
2. **Pas d'indication « en bonne voie »** sur une sélection en cours : Netanya (+3,0) à 0-0 et
   « Katamon moins de 2,5 buts » à 0-0 sont toutes deux gagnantes à cet instant, mais rien
   ne le montre (les bookmakers mettent un point vert). **Piste** : « gagnante pour
   l'instant » / « perdante pour l'instant » d'après le score, sans changer le règlement.
3. Chance du coupon en direct : absente (attendu, étape 1 de la proposition non faite).
