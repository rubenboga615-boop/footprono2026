# Coupons en direct à la mi-temps, à la 60e et à la 75e — étude du 13/11/2026

Action de la console « Vérifier les coupons en direct (mi-temps, 60e, 75e) », lancée par le
fondateur le 13/11/2026 à 01:23 sur le serveur (commit `93b74ad`). Saisons 2023-2025,
prévisions d'avant-match rejouées hors échantillon, **13 347 matchs** (aucun écarté).
Modèle du direct appris le 11/11/2026 ; marchés retirés en 2e période : « Buts d'une
équipe », « Les deux marquent ». Règle : 3 points près ou deux erreurs types.

## Résultat : juste aux trois moments

| Moment | Profil | Sélections (annoncé → gagné) | Combinés de 2 matchs | Combinés de 3 matchs |
|---|---|---|---|---|
| Mi-temps | Sûr | 12 540 · 83,0 → 83,6 % | 68,8 → 70,0 % | 57,1 → 58,8 % |
| | Équilibré | 10 389 · 70,4 → 70,9 % | 49,6 → 50,4 % | 34,9 → 36,1 % |
| | Audacieux | 11 276 · 55,4 → 55,9 % | 30,7 → 31,0 % | 17,0 → 17,0 % |
| 60e | Sûr | 11 434 · 84,0 → 83,8 % | 70,5 → 69,9 % | 59,2 → 58,5 % |
| | Équilibré | 11 504 · 71,2 → 71,4 % | 50,7 → 51,1 % | 36,1 → 36,7 % |
| | Audacieux | 5 605 · 55,2 → 56,8 % | 30,5 → 32,6 % | 16,9 → 18,0 % |
| 75e | Sûr | 11 378 · 84,9 → 84,7 % | 72,0 → 71,5 % | 61,1 → 60,8 % |
| | Équilibré | 4 878 · 67,8 → 66,6 % | 46,0 → 44,4 % | 31,2 → 29,1 % |
| | Audacieux | 10 774 · 54,7 → 54,2 % | 30,0 → 29,8 % | 16,4 → 15,8 % |

Les combinés de plusieurs matchs (une sélection par match) sont justes : la chance du
combiné = produit des chances, vérifié.

## Deux marchés « à revoir », dans un seul profil chacun

| Moment | Profil | Marché | Sélections | Annoncé → gagné | Sens |
|---|---|---|---|---|---|
| 60e | Audacieux | Buts du match (plus/moins) | 1 637 | 57,7 → 60,8 % | le moteur **sous-estime** (prudent) |
| 75e | Équilibré | Buts du match (plus/moins) | 392 | 61,9 → 56,9 % | le moteur **surestime** (peu de sélections) |

Proposition : ne pas proposer « Buts du match » dans ces deux cas (règle du 11/11 : aucun
chiffre plutôt qu'un chiffre faux), le reste inchangé.
