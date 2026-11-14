# Propositions du designer — 14 novembre 2026 — à valider

Quatre améliorations, une idée chacune. Avant : captures du site en ligne le 14/11 au matin
(compte de test Premium, argent fictif). Après : maquettes HTML, même style que
`2-corrigees/` (fond `#0E0B1A`, cartes `#1A1530`, violet `#6D4AFF`, Inter, écrans 390 × 844).
Les chiffres sont ceux des vrais coupons du 12 et du 14/11. Les contours verts en pointillés
montrent ce qui change.

Ouvrir `propositions.html` dans Chrome (tout côte à côte), ou regarder les PNG.

| # | Sujet | Avant | Après |
|---|---|---|---|
| P1 | Coupon intelligent : avertir quand le moteur est sous la cote | `avant/P1-avant-coupon-intelligent.png` | `P1a-apres.png` (sous la cote), `P1b-apres.png` (au-dessus), `P1-avant-apres.png` |
| P2 | Coupons du jour : chance selon la cote sur chaque carte, et phrase quand l'Audacieux n'est pas plus risqué | `avant/P2-avant-coupons-du-jour.png` | `P2a-apres.png` (14/11), `P2b-apres.png` (cas du 12/11), `P2-avant-apres.png` |
| P3 | Page d'accueil : logo Ballon-jauge B3 devant « FootProba » | `avant/P3-avant-accueil.png` | `P3a-apres.png`, `P3-avant-apres.png` |
| P4 | Notifications : date, « ton pari » ou « ton coupon », une seule notification par palier de montante, un seul ⏰ | `avant/P4-avant-notifications.png` | `P4a-apres.png`, `P4-avant-apres.png` |

Règle de couleur commune (P1, P2), la même que la montante et le coupon en direct :
**ambre** si le moteur est au moins 2 points sous la cote, **vert** s'il est au moins 2
points au-dessus, **gris** (« d'accord avec la cote ») sinon. Le vert ne promet jamais de
gain (« ne garantit rien »).

Pas refait : le Mode Montante (`8-mode-montante/`) et le coupon en direct (filtre « chance du
moteur ≥ cote + 3 points » déjà décidé par le fondateur le 13/11, `9ef823e`).

Détail, effort et raisons : `docs/AUDIT_EQUIPE/design-2026-11-14.md`.
