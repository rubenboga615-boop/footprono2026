# Étude complète de FootProba et nouveau visage — 20 novembre 2026

Demande du fondateur : étudier toute l'application, trouver ce qui doit être réparé, et
proposer un nouveau visage (tous les écrans) et de nouvelles fonctionnalités, en maquettes.
Rien n'a été modifié dans le code.

Sources :
- 12 jours d'utilisation comme joueur (`AUDIT_JEU_2026-11-09` à `-19`), tests du direct
  (`AUDIT_DIRECT_*`) ;
- audit d'équipe du 14/11 (`AUDIT_EQUIPE/`) ;
- nouvel audit sécurité et logique du 20/11 (`AUDIT_EQUIPE/securite-2026-11-20.md`).

## 1. Ce qui doit être réparé (encore ouvert le 20/11)

### 🔴 Urgent
1. **Version web pas republiée depuis le 17/11 à 02:22.** Les corrections de Mon bilan, de
   la Fiabilité des sélections, de la montante terminée, de « pour 30 jours » et du Coupon
   intelligent gardé ne sont pas visibles sur le web.
2. **`/reliability` peut être forcée à recalculer** (13 à 14 s par appel) en changeant `since`
   ou `recent` : même risque que la page « qualité » fermée le 14/11. Fermer ces réglages
   au public. *(Audit sécurité du 20/11, point important.)*

### 🟠 Important
3. **Moteur des sélections nationales trop sûr de lui** : quand il dépasse la cote de 5 à
   15 points, il gagne moins souvent que la cote ne le dit (21 % et 33 % gagnés, −11 640 F
   à 1 000 F par pari sur 92 matchs). Ne plus présenter ces écarts comme des occasions, et
   mesurer les autres marchés. *(`AUDIT_VERIF_2026-11-18.md`)*
4. **Coupons intelligents presque toujours sous la cote** (du 17 au 19/11, tous les profils)
   sans avertissement à l'écran. Le choix par tranche de chance ignore la cote. *(Maquette 11
   et maquette P1 du designer.)*
5. **Comparaison des moteurs** : chaque coupon généré est enregistré sans limite et sans
   joueur ; un seul joueur peut décider du verdict moteur 1 / moteur 2 ; la page est ouverte
   aux comptes gratuits. *(Audit du 20/11, point moyen.)*
6. **Accueil** : écran noir de 3 s, bandeau « installer » et fenêtre « aider à améliorer »
   dès l'arrivée. *(Visuel 14/11, maquettes 1 à 3.)*
7. **Boutons trop petits** (cotes de 35 px, liens de 21 px), dates cachées sous
   « Championnats » sur téléphone. *(Maquette 6.)*
8. **Analyse d'un match** : carte vide, moyennes sans nom d'équipe. *(Maquette 9.)*
9. **Règlement des marchés de 1re mi-temps** : à revérifier en vrai (le 13/11, 20 à 25 min
   après la pause).
10. **Inscription sans vérification du numéro.** *(Maquette 2.)*

### 🟢 Faible
11. « Score corrigé » quand le solde est vide : un gain peut être payé deux fois si le score
    change deux fois (`settlement.py` l. 628 et 640, argent fictif).
12. Verrou du rattrapage : il bloque le règlement jusqu'à 1 h si le worker s'arrête, et il est
    effacé sans vérifier à qui il appartient.
13. L'export « sans données personnelles » contient le nom du canal d'alertes ntfy.
14. Très grands nombres dans les adresses : erreur 500 au lieu de 400.
15. À vérifier au prochain match : « Irlande » au lieu de « Rep. Of Ireland », gain exact sur
    un combiné à cote arrondie, minute « 90+X' ».

### Déjà corrigé et vérifié (rien à faire)
Pages internes fermées, double pari sur un palier impossible, paiements revérifiés et
limités, « Tout rattraper », notifications pendant les matchs, rappels de chaque match,
élision, date dans « tout se joue sur ».

## 2. Nouveau visage (maquettes `docs/maquettes/12-nouveau-visage/`)

**Les 4 idées** :
1. **Fond bleu nuit** (#0B0F1A), cartes #131A2A ; le violet du logo (#7C5CFF) est réservé aux
   actions ; menthe = au-dessus de la cote ou gagné, corail = sous la cote ou perdu, ambre =
   prudence.
2. **Une pastille unique « moteur contre cote »** (▲ +9 pts / ≈ cote / ▼ −8 pts) sur chaque
   sélection, coupon, alerte et proposition. C'est le langage commun de toute l'application :
   le joueur sait toujours si le moteur bat le bookmaker.
3. **Nouvelle barre du bas** : Aujourd'hui · Matchs · **Créer** (bouton central, qui regroupe
   le Coupon intelligent, les Coupons du jour, la Montante, le Coupon en direct, Composer et
   la Grosse cote) · Paris · Moi.
4. **Le gain et le risque toujours côte à côte** (« si ça passe / si ça rate »), et des écrans
   « rien aujourd'hui » à part entière.

34 écrans : les 27 écrans existants redessinés, et 7 nouveaux.

## 3. Nouvelles fonctionnalités proposées (avec maquette)

| Idée | Maquette | Pourquoi |
|---|---|---|
| **Aujourd'hui** : accueil « que faire maintenant », qui assume de dire « rien » | 4, 5 | le joueur arrivait sur 40 matchs sans repère ; la plupart des jours, rien ne bat la cote |
| **Alerte de cote** : prévenir quand la cote dépasse la chance du moteur | 29 | trouver la vraie valeur sans parcourir tous les matchs |
| **Mon plan de jeu** : budget, limite de perte, pause | 30 | jeu responsable concret, qui protège aussi FootProba (Google Play, loi) |
| **Pourquoi ce choix ?** : les raisons d'une chance, en mots simples | 31 | confiance ; le joueur comprend au lieu de suivre |
| **Bilan de la semaine** chaque lundi | 32 | fidéliser sans pousser à parier |
| **Inviter un ami** : 30 jours offerts quand l'ami paie | 33 | croissance sans publicité (le business déconseille la pub payante pour l'instant) |
| **Mode simple** pour débutants | 34 | un nouveau joueur n'a besoin que des coupons du jour et du résultat |
| **Premiers pas** en 3 cartes | 3 | expliquer « chance » et « moteur contre cote » en 20 secondes |
| **Histoire d'un pari** en frise | 19 | comprendre un règlement (rattrapage, but annulé) sans chercher |
| **Historique des cotes** avec la ligne du moteur | 27 | voir si le marché se rapproche du moteur |
| **Équipes suivies** (★) | 6, 26 | une liste de matchs à soi |

## 4. Ordre conseillé

1. Republier la version web et fermer `/reliability` (points 1 et 2).
2. Avertissement « moteur sous la cote » partout (points 3 et 4) : c'est la pastille du
   nouveau visage. On peut commencer par elle seule, sur l'écran actuel.
3. Valider le nouveau visage par étapes : couleurs et pastille, puis barre du bas et
   « Aujourd'hui », puis les nouvelles fonctionnalités (Mon plan de jeu en premier).
