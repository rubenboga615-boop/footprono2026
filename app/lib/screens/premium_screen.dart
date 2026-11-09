// « Passer Premium » (maquette C9) et « Payer avec Wave » (maquette C8), validées le
// 07/11/2026 : deux écrans entiers à la place des fenêtres. Mêmes règles qu'avant : prix et
// moyens de paiement donnés par le serveur, payé une fois, sans renouvellement automatique.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../desktop/layout.dart';
import '../format.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/maquette.dart';

/// Ce que Premium ajoute, sans ambiguïté (les ✓ seuls laissaient croire que la version
/// gratuite avait déjà tout) : profil (N4) et « Passer Premium » (C9).
class PremiumTable extends StatelessWidget {
  const PremiumTable({super.key});

  static const rows = [
    ('Chances 1-N-2, buts, les 2 marquent', true),
    ('Coupons du jour : profil, cote, bilan', true),
    ('Coupons du jour : sélections et code 1xBet', false),
    ('Coupon intelligent (ta cote, ton profil)', false),
    ('Corners, cartons, tirs, handicaps', false),
    ('Analyse du match (forme, face-à-face)', false),
    ('Suggestions de montante', false),
  ];

  @override
  Widget build(BuildContext context) {
    // Maquettes N4 et C9 : ✓ vert, cadenas gris au trait, colonnes de 62, texte 13.
    Widget cell(bool ok) => SizedBox(
      width: 62,
      child: Center(
        child: ok
            ? const Icon(Icons.check_rounded, size: 15, color: Fp.win)
            : const Icon(Icons.lock_outline_rounded, size: 15, color: Fp.muted),
      ),
    );
    const line = BoxDecoration(
      border: Border(bottom: BorderSide(color: Fp.divider)),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: line,
          child: Row(
            children: [
              const Spacer(),
              for (final t in const ['Gratuit', 'Premium'])
                SizedBox(
                  width: 62,
                  child: Text(
                    t,
                    textAlign: TextAlign.center,
                    style: Fp.body(12, weight: FontWeight.w600, color: Fp.muted),
                  ),
                ),
            ],
          ),
        ),
        for (final (label, free) in rows)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 9),
            decoration: line,
            child: Row(
              children: [
                Expanded(child: Text(label, style: Fp.body(13))),
                cell(free),
                cell(true),
              ],
            ),
          ),
      ],
    );
  }
}

/// Choix du moyen de paiement (ceux du serveur, et le Wave manuel s'il est proposé).
Future<void> openPremiumPurchase(BuildContext context, Plan plan) async {
  final state = context.read<AppState>();
  final offer = await guard(context, state.paymentMethods);
  if (offer == null || !context.mounted) return;
  await Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => PremiumScreen(offer: offer, plan: plan),
    ),
  );
}

class PremiumScreen extends StatelessWidget {
  const PremiumScreen({super.key, required this.offer, required this.plan});
  final Json offer;
  final Plan plan;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final price = offer['price'] as int;
    final currency = offer['currency'] as String;
    final amount = money(price, currency);
    final methods = [for (final m in offer['methods'] as List) m as Json];
    final manual = offer['manual'] as Json?;
    final me = state.me!;
    final account = 'n° ${me.id}${me.phone != null ? ' (${me.phone})' : ''}';

    // Une option de paiement : bouton, puis ce qui se passe après, en petit.
    final options = <(String, String, VoidCallback)>[
      for (final m in methods)
        (
          'Payer avec ${m['label']}',
          'Premium activé dès la confirmation du paiement',
          () => guard(context, () => state.buyPremium(m['id'] as String)),
        ),
      if (manual != null)
        (
          methods.isEmpty ? 'Payer avec Wave' : 'Payer avec Wave (envoi au numéro FootProba)',
          'Premium activé après vérification de l\'envoi',
          () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => WaveScreen(amount: amount, number: manual['wave_number'] as String),
            ),
          ),
        ),
      // Aucun paiement en ligne réglé sur le serveur : jamais d'impasse (essai du 07/11/2026),
      // l'abonnement passe par WhatsApp et Premium est activé depuis la console.
      if (methods.isEmpty && manual == null)
        (
          'Écrire sur WhatsApp',
          'Le paiement dans l\'application arrive bientôt : on t\'indique comment payer par Mobile '
              'Money et on active Premium dès la réception.',
          () => state.openSupport(
            'Bonjour FootProba, je veux passer Premium ($amount). Mon compte : $account.',
          ),
        ),
    ];

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: pagePadding(context, 16, 32, maxWidth: 640),
          children: [
            const BackHeader('Passer', 'Premium'),
            const SizedBox(height: 12),
            MCard(
              highlight: true,
              color: Fp.cardHigh,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Premium · 30 jours', style: Fp.title(18)),
                  const SizedBox(height: 2),
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: currency == 'XOF' ? '${thousands(price)} F ' : '$amount ',
                          style: Fp.title(30, weight: FontWeight.w800),
                        ),
                        if (currency == 'XOF')
                          TextSpan(
                            text: 'CFA',
                            style: Fp.body(12, color: Fp.muted),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Payé une fois, sans renouvellement automatique'
                    '${plan.premium ? ', à la suite de ta période en cours' : ''}. Ce paiement est réel, '
                    'contrairement aux paris, en argent fictif.',
                    style: Fp.body(12.5, color: Fp.muted, height: 1.4),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            const MCard(child: PremiumTable()),
            for (final (i, (label, note, onTap)) in options.indexed) ...[
              SizedBox(height: i == 0 ? 16 : 12),
              MButton(label, secondary: i > 0, onPressed: onTap),
              const SizedBox(height: 6),
              Text(
                note,
                textAlign: TextAlign.center,
                style: Fp.body(12.5, color: Fp.muted, height: 1.4),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Wave sans compte marchand : le joueur envoie le montant au numéro de FootProba puis
/// la capture sur WhatsApp ; l'administrateur vérifie la réception et active Premium.
class WaveScreen extends StatelessWidget {
  const WaveScreen({super.key, required this.amount, required this.number});
  final String amount;
  final String number;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    final me = state.me!;
    final account = 'compte n° ${me.id}${me.phone != null ? ' (${me.phone})' : ''}';
    Widget step(int n, Widget text, [Widget? below]) => MCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Tag('$n', color: Fp.lilac, background: Fp.cardHigh),
              const SizedBox(width: 10),
              Expanded(child: text),
            ],
          ),
          ?below,
        ],
      ),
    );
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: ListView(
          padding: pagePadding(context, 16, 32, maxWidth: 640),
          children: [
            const BackHeader('Payer avec', 'Wave'),
            const SizedBox(height: 12),
            step(
              1,
              Text.rich(
                TextSpan(
                  children: [
                    const TextSpan(text: 'Dans Wave, envoie exactement '),
                    TextSpan(
                      text: amount,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const TextSpan(text: ' au numéro officiel de FootProba (le même que l\'aide WhatsApp) :'),
                  ],
                ),
                style: Fp.body(14, height: 1.4),
              ),
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Material(
                  color: Fp.background,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                    side: const BorderSide(color: Fp.accent2, width: 1.5),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () async {
                      await Clipboard.setData(ClipboardData(text: number));
                      showMessage('Numéro copié');
                    },
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      child: Row(
                        children: [
                          // Groupé deux par deux : plus facile à recopier dans Wave.
                          Expanded(
                            child: Text(groupedPhone(number), style: Fp.body(17, weight: FontWeight.w700)),
                          ),
                          Text(
                            'Copier',
                            style: Fp.body(13, weight: FontWeight.w600, color: Fp.lilac),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            step(
              2,
              Text(
                'Envoie la capture du reçu Wave sur WhatsApp, avec le bouton ci-dessous.',
                style: Fp.body(14, height: 1.4),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Premium est activé sur ton $account dès que la réception est vérifiée, en général dans '
              'la journée. Tu reçois une notification.',
              style: Fp.body(13, color: Fp.muted, height: 1.4),
            ),
            const SizedBox(height: 24),
            MButton(
              'Envoyer la capture',
              onPressed: () {
                state.markWavePending();
                Navigator.of(context).popUntil((r) => r.isFirst);
                state.openSupport(
                  'Bonjour FootProba, j\'ai payé Premium ($amount) par Wave au $number. '
                  'Mon $account. Voici la capture du reçu :',
                );
              },
            ),
            const SizedBox(height: 10),
            MButton('Fermer', secondary: true, onPressed: () => Navigator.of(context).maybePop()),
          ],
        ),
      ),
    );
  }
}
