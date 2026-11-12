# Audit du direct — version 212 (notifications pendant les matchs, « Encore au moins un but »)

## 12/11, 22 h 12 GMT — Mise en ligne, contrôles hors match

| Point | Constat | Verdict |
|---|---|---|
| Serveur | `/api/v1/health` → commit `c273de8`, qui contient `6caf8da` (seuls des rapports d'audit ont été ajoutés après) | à jour |
| Version web | `main.dart.js` du 12/11 22:08 ; contient « Encore au moins un but », « Au moins un but dans le match », « chances de tenir », « Pendant mes matchs » | 212 en ligne |
| Nouvelle colonne joueur | `/me` renvoie `match_notifications: "all"` | présente |
| Profil → Pendant mes matchs | ligne « Pendant mes matchs · Tout », feuille avec Tout / Validé ou perdu / Rien et la mention « Rien sur le téléphone entre 23 h et 8 h » | conforme |
| Enregistrement du réglage | « Validé ou perdu » → l'API renvoie `results` ; retour à « Tout » → `all` | conforme |
| `/metrics`, en-têtes | 404 ; CSP et HSTS présents | toujours bons |

Pas de match en cours à cette heure : les notifications pendant les matchs et la carte
« Chances en direct » seront vérifiées le 13/11. Matchs prévus :
- Burkina Faso – Mauritanie (16:00, pari 58) ;
- Moldavie – Kazakhstan (17:00, dernier match du pari 58) ;
- Écosse – Macédoine du Nord (19:45, pari 57).
