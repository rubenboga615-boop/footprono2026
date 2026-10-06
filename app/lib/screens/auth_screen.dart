import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../state/app_state.dart';
import '../theme.dart';
import '../widgets/install_tip.dart';
import 'server_dialog.dart';

const countries = {
  'BJ': 'Bénin',
  'BF': 'Burkina Faso',
  'CI': "Côte d'Ivoire",
  'GW': 'Guinée-Bissau',
  'ML': 'Mali',
  'NE': 'Niger',
  'SN': 'Sénégal',
  'TG': 'Togo',
};

const dialCodes = {
  'BJ': '+229',
  'BF': '+226',
  'CI': '+225',
  'GW': '+245',
  'ML': '+223',
  'NE': '+227',
  'SN': '+221',
  'TG': '+228',
};

/// Pays proposé d'abord (pays et indicatif) : la Côte d'Ivoire.
const defaultCountry = 'CI';

/// Numéro complet : indicatif choisi + numéro local. Un numéro déjà international
/// (« +… » ou « 00… ») est gardé tel quel.
String fullPhone(String country, String local) {
  final t = local.trim();
  if (t.startsWith('+') || t.startsWith('00')) return t;
  return '${dialCodes[country]} $t';
}

enum _Mode { welcome, login, register }

/// Connexion : avec Google (Android) ou avec le numéro ; inscription par numéro ;
/// première connexion Google (pays, 18 ans).
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  late _Mode mode = context.read<AppState>().google != null ? _Mode.welcome : _Mode.login;
  bool busy = false;
  bool adult = false;
  bool showPassword = false;
  String country = defaultCountry;
  String dial = defaultCountry;
  String? error;
  final phone = TextEditingController();
  final password = TextEditingController();
  final name = TextEditingController();

  @override
  void dispose() {
    phone.dispose();
    password.dispose();
    name.dispose();
    super.dispose();
  }

  void _go(_Mode m) => setState(() {
    mode = m;
    error = null;
  });

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _submit() => _run(() async {
    final state = context.read<AppState>();
    if (mode == _Mode.register && !adult) {
      throw ApiException(400, 'adult', 'Il faut avoir 18 ans ou plus pour utiliser FootProba.');
    }
    if (phone.text.trim().isEmpty) {
      throw ApiException(400, 'phone', 'Écris ton numéro de téléphone.');
    }
    final number = fullPhone(dial, phone.text);
    if (mode == _Mode.register) {
      await state.register(
        phone: number,
        password: password.text,
        name: name.text.trim(),
        country: country,
        adult: adult,
      );
    } else {
      await state.login(number, password.text);
    }
  });

  Future<void> _google() => _run(() async {
    await context.read<AppState>().signInWithGoogle();
  });

  void _forgotPassword() {
    final number = phone.text.trim().isEmpty ? '' : ' Mon numéro : ${fullPhone(dial, phone.text)}.';
    context.read<AppState>().openSupport("Bonjour, j'ai oublié mon mot de passe FootProba.$number");
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final signup = state.googleSignup;
    final Widget card;
    if (signup != null) {
      card = _GoogleProfile(signup: signup);
    } else {
      card = switch (mode) {
        _Mode.welcome => _welcome(),
        _Mode.login || _Mode.register => _phoneForm(state),
      };
    }
    final showBack = signup == null && mode != _Mode.welcome && state.google != null;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      if (showBack)
                        IconButton.outlined(
                          tooltip: 'Retour',
                          onPressed: busy ? null : () => _go(_Mode.welcome),
                          icon: const Icon(Icons.chevron_left_rounded),
                        )
                      else
                        const FpLogo(size: 20),
                    ],
                  ),
                  const SizedBox(height: 34),
                  const InstallTip(margin: EdgeInsets.only(bottom: 16)),
                  card,
                  const SizedBox(height: 22),
                  Text(
                    '18 ans et plus · argent fictif, aucun pari réel',
                    textAlign: TextAlign.center,
                    style: Fp.body(12, color: Fp.text3, height: 1.5),
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    alignment: WrapAlignment.center,
                    children: [
                      const _LegalLink('Conditions', '/conditions'),
                      Text('  ·  ', style: Fp.body(12, color: Fp.text3)),
                      const _LegalLink('Confidentialité', '/confidentialite'),
                    ],
                  ),
                  if (serverChoice) ...[
                    const SizedBox(height: 18),
                    TextButton.icon(
                      onPressed: () => showServerDialog(context),
                      icon: const Icon(Icons.dns_outlined, size: 18),
                      label: Text('Serveur : ${state.api.baseUrl}', overflow: TextOverflow.ellipsis),
                      style: TextButton.styleFrom(foregroundColor: Fp.text3),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _welcome() {
    return GlassCard.hero(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Center(child: IconSquare(Icons.verified_user_outlined, size: 46, iconSize: 22, radius: 14)),
          const SizedBox(height: 16),
          const Center(child: TwoToneTitle('Bienvenue', '!', size: 28)),
          const SizedBox(height: 6),
          Text(
            'Les probabilités des matchs, calculées sans regarder les cotes.',
            textAlign: TextAlign.center,
            style: Fp.body(14, color: Fp.text2, height: 1.45),
          ),
          const SizedBox(height: 24),
          GlowButton(
            onPressed: busy ? null : _google,
            busy: busy,
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                GoogleMark(size: 28),
                SizedBox(width: 12),
                Flexible(child: Text('Continuer avec Google', overflow: TextOverflow.ellipsis)),
                SizedBox(width: 10),
                Icon(Icons.arrow_forward_rounded, size: 20),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'Un appui, aucun mot de passe à retenir.',
            textAlign: TextAlign.center,
            style: Fp.body(12, color: Fp.text3),
          ),
          if (error != null) ...[
            const SizedBox(height: 12),
            Text(
              error!,
              textAlign: TextAlign.center,
              style: Fp.body(13, color: Fp.lossText, height: 1.4),
            ),
          ],
          const SizedBox(height: 18),
          const OrDivider('OU AVEC TON NUMÉRO'),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: busy ? null : () => _go(_Mode.login),
            icon: const Icon(Icons.phone_iphone_rounded, size: 18),
            label: const Text('Numéro de téléphone'),
          ),
        ],
      ),
    );
  }

  Widget _phoneForm(AppState state) {
    final register = mode == _Mode.register;
    return GlassCard.hero(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 22),
            child: register
                ? const TwoToneTitle('Créer un', 'compte', size: 26)
                : const TwoToneTitle('Bon', 'retour', size: 26),
          ),
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsets.only(left: 22),
            child: Text(
              register ? 'Rejoins FootProba avec ton numéro.' : 'Connecte-toi avec ton numéro.',
              style: Fp.body(13, color: Fp.text2, height: 1.4),
            ),
          ),
          const SizedBox(height: 18),
          if (register) ...[
            FpField(
              label: 'Nom affiché',
              controller: name,
              icon: Icons.person_outline_rounded,
              hint: 'Prénom Nom',
              textCapitalization: TextCapitalization.words,
              maxLength: 40,
            ),
            const SizedBox(height: 14),
            CountryPicker(
              value: country,
              onChanged: (v) => setState(() {
                country = v;
                dial = v; // l'indicatif suit le pays
              }),
            ),
            const SizedBox(height: 14),
          ],
          FpField(
            label: 'Numéro de téléphone',
            controller: phone,
            hint: '07 00 00 00 00',
            keyboardType: TextInputType.phone,
            prefix: DialPicker(value: dial, onChanged: (v) => setState(() => dial = v)),
          ),
          const SizedBox(height: 14),
          FpField(
            label: 'Mot de passe',
            controller: password,
            icon: Icons.lock_outline_rounded,
            obscure: !showPassword,
            helper: register ? '8 caractères au minimum' : null,
            onSubmitted: (_) => busy ? null : _submit(),
            suffix: IconButton(
              tooltip: showPassword ? 'Masquer' : 'Afficher',
              icon: Icon(showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined),
              onPressed: () => setState(() => showPassword = !showPassword),
            ),
          ),
          if (!register)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(onPressed: _forgotPassword, child: const Text('Mot de passe oublié ?')),
            ),
          if (register) ...[
            const SizedBox(height: 14),
            AdultCheck(value: adult, onChanged: (v) => setState(() => adult = v)),
            const SizedBox(height: 8),
            Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  'En créant un compte, tu acceptes les ',
                  style: Fp.body(12, color: Fp.text2, height: 1.4),
                ),
                const _LegalLink('conditions d\'utilisation', '/conditions'),
                Text(' et la ', style: Fp.body(12, color: Fp.text2, height: 1.4)),
                const _LegalLink('politique de confidentialité', '/confidentialite'),
                Text('.', style: Fp.body(12, color: Fp.text2, height: 1.4)),
              ],
            ),
          ],
          if (error != null) ...[
            const SizedBox(height: 12),
            Text(error!, style: Fp.body(13, color: Fp.lossText, height: 1.4)),
          ],
          const SizedBox(height: 16),
          GlowButton(
            onPressed: busy ? null : _submit,
            busy: busy,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(register ? 'Créer mon compte' : 'Se connecter'),
                const SizedBox(width: 10),
                const Icon(Icons.arrow_forward_rounded, size: 20),
              ],
            ),
          ),
          if (state.google != null) ...[
            const SizedBox(height: 18),
            const OrDivider('OU CONTINUER AVEC'),
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: busy ? null : _google,
              icon: const GoogleMark(size: 20, badge: false),
              label: const Text('Google'),
            ),
          ],
          const SizedBox(height: 14),
          Center(
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  register ? 'Déjà un compte ? ' : 'Pas encore de compte ? ',
                  style: Fp.body(14, color: Fp.text2),
                ),
                GestureDetector(
                  onTap: busy ? null : () => _go(register ? _Mode.login : _Mode.register),
                  child: Text(
                    register ? 'Se connecter' : 'Créer un compte',
                    style: Fp.body(14, color: Fp.accentLight, weight: FontWeight.w700),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Première connexion avec Google : pays et âge, une seule fois.
class _GoogleProfile extends StatefulWidget {
  const _GoogleProfile({required this.signup});
  final GoogleSignup signup;

  @override
  State<_GoogleProfile> createState() => _GoogleProfileState();
}

class _GoogleProfileState extends State<_GoogleProfile> {
  String country = defaultCountry;
  bool adult = false;
  bool busy = false;
  String? error;

  Future<void> _start() async {
    if (!adult) {
      setState(() => error = 'Il faut avoir 18 ans ou plus pour utiliser FootProba.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await context.read<AppState>().registerWithGoogle(country: country, adult: adult);
    } on ApiException catch (e) {
      if (mounted) setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.signup;
    final initial = (s.name.isNotEmpty ? s.name : s.email).characters.first.toUpperCase();
    return GlassCard.hero(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              padding: const EdgeInsets.fromLTRB(6, 6, 14, 6),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: Fp.line),
                color: Colors.black.withValues(alpha: 0.3),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircleAvatar(
                    radius: 15,
                    backgroundColor: Fp.accentSoft,
                    child: Text(initial, style: Fp.title(14, color: Fp.accentLight)),
                  ),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(
                      s.email,
                      overflow: TextOverflow.ellipsis,
                      style: Fp.body(13, color: Fp.textSoft),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Center(child: TwoToneTitle('Presque', 'prêt', size: 28)),
          const SizedBox(height: 6),
          Text(
            'Deux réponses, une seule fois.',
            textAlign: TextAlign.center,
            style: Fp.body(14, color: Fp.text2),
          ),
          const SizedBox(height: 18),
          CountryPicker(value: country, onChanged: (v) => setState(() => country = v)),
          const SizedBox(height: 16),
          AdultCheck(value: adult, onChanged: (v) => setState(() => adult = v)),
          if (error != null) ...[
            const SizedBox(height: 12),
            Text(error!, style: Fp.body(13, color: Fp.lossText, height: 1.4)),
          ],
          const SizedBox(height: 18),
          GlowButton(
            onPressed: busy ? null : _start,
            busy: busy,
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [Text('Commencer'), SizedBox(width: 10), Icon(Icons.arrow_forward_rounded, size: 20)],
            ),
          ),
          const SizedBox(height: 6),
          TextButton(
            onPressed: busy ? null : () => context.read<AppState>().cancelGoogleSignup(),
            child: const Text('Annuler'),
          ),
        ],
      ),
    );
  }
}

/// Écran « Connexion réussie », juste après une connexion avec Google.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    const green = Fp.win;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: GlassCard.hero(
                child: Column(
                  children: [
                    Container(
                      width: 46,
                      height: 46,
                      decoration: BoxDecoration(
                        color: green.withValues(alpha: 0.1),
                        border: Border.all(color: green.withValues(alpha: 0.55)),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [BoxShadow(color: green.withValues(alpha: 0.3), blurRadius: 22)],
                      ),
                      child: const Icon(Icons.verified_user_outlined, color: green, size: 22),
                    ),
                    const SizedBox(height: 20),
                    Container(
                      width: 150,
                      height: 150,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: green, width: 3),
                        boxShadow: [BoxShadow(color: green.withValues(alpha: 0.35), blurRadius: 40)],
                      ),
                      child: Center(
                        child: Container(
                          width: 66,
                          height: 66,
                          decoration: BoxDecoration(
                            border: Border.all(color: green, width: 2),
                            borderRadius: BorderRadius.circular(18),
                          ),
                          child: const Icon(Icons.check_rounded, color: green, size: 38),
                        ),
                      ),
                    ),
                    const SizedBox(height: 22),
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(text: 'Connexion ', style: Fp.title(28)),
                          TextSpan(
                            text: 'réussie',
                            style: Fp.title(28, color: green),
                          ),
                        ],
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Bienvenue, ${state.me?.displayName ?? ''}. Les probabilités du jour t\'attendent.',
                      textAlign: TextAlign.center,
                      style: Fp.body(14, color: Fp.text2, height: 1.45),
                    ),
                    const SizedBox(height: 22),
                    SizedBox(
                      width: double.infinity,
                      child: GlowButton(
                        color: green,
                        foreground: const Color(0xFF06240F),
                        onPressed: state.closeWelcome,
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.shield_outlined, size: 18),
                            SizedBox(width: 10),
                            Flexible(child: Text('Voir les matchs du jour', overflow: TextOverflow.ellipsis)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Bouton principal lumineux (halo de sa couleur).
class GlowButton extends StatelessWidget {
  const GlowButton({
    super.key,
    required this.onPressed,
    required this.child,
    this.busy = false,
    this.color = Fp.accent,
    this.foreground = Colors.white,
  });
  final VoidCallback? onPressed;
  final Widget child;
  final bool busy;
  final Color color;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: Fp.radius14,
        boxShadow: onPressed == null
            ? null
            : [BoxShadow(color: color.withValues(alpha: 0.38), blurRadius: 30, offset: const Offset(0, 10))],
      ),
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: color,
          foregroundColor: foreground,
          minimumSize: const Size.fromHeight(54),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          textStyle: Fp.body(15, weight: FontWeight.w800),
        ),
        child: busy
            ? SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2, color: foreground),
              )
            : child,
      ),
    );
  }
}

/// Séparateur « OU … » en petites capitales espacées.
class OrDivider extends StatelessWidget {
  const OrDivider(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Expanded(child: Divider(color: Fp.line12)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Text(
            text,
            style: Fp.body(10, color: Fp.text4, weight: FontWeight.w700).copyWith(letterSpacing: 1.4),
          ),
        ),
        const Expanded(child: Divider(color: Fp.line12)),
      ],
    );
  }
}

/// Choix du pays (Côte d'Ivoire par défaut).
class CountryPicker extends StatelessWidget {
  const CountryPicker({super.key, required this.value, required this.onChanged});
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Pays',
          style: Fp.body(13, weight: FontWeight.w600, color: Fp.textStrong),
        ),
        const SizedBox(height: 7),
        DropdownButtonFormField<String>(
          isExpanded: true,
          initialValue: value,
          dropdownColor: const Color(0xFF1A1626),
          borderRadius: Fp.radius14,
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.public_rounded, size: 20),
            suffixText: 'F CFA',
          ),
          items: [
            for (final e in countries.entries)
              DropdownMenuItem(
                value: e.key,
                child: Text(e.value, style: Fp.body(15)),
              ),
          ],
          onChanged: (v) => onChanged(v ?? value),
        ),
      ],
    );
  }
}

/// Indicatif du pays devant le numéro (+225 par défaut) : le joueur tape seulement son numéro.
class DialPicker extends StatelessWidget {
  const DialPicker({super.key, required this.value, required this.onChanged});
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      tooltip: 'Indicatif du pays',
      initialValue: value,
      color: const Color(0xFF1A1626),
      onSelected: onChanged,
      itemBuilder: (_) => [
        for (final e in countries.entries)
          PopupMenuItem(
            value: e.key,
            child: Row(
              children: [
                SizedBox(
                  width: 52,
                  child: Text(dialCodes[e.key]!, style: Fp.body(14, weight: FontWeight.w700)),
                ),
                Text(e.value, style: Fp.body(14, color: Fp.text2)),
              ],
            ),
          ),
      ],
      child: Padding(
        padding: const EdgeInsets.only(left: 14, right: 4),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(dialCodes[value]!, style: Fp.body(15, weight: FontWeight.w700)),
            const Icon(Icons.arrow_drop_down_rounded, size: 22, color: Fp.text2),
            Container(width: 1, height: 22, color: Fp.line, margin: const EdgeInsets.only(left: 4)),
          ],
        ),
      ),
    );
  }
}

/// Case « J'ai 18 ans ou plus » (obligatoire).
class AdultCheck extends StatelessWidget {
  const AdultCheck({super.key, required this.value, required this.onChanged});
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => onChanged(!value),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 20,
            height: 20,
            child: Checkbox(value: value, onChanged: (v) => onChanged(v ?? false)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("J'ai 18 ans ou plus", style: Fp.body(14, weight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(
                  'Obligatoire. Argent fictif, aucun pari réel.',
                  style: Fp.body(12, color: Fp.text3, height: 1.4),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// « G » de Google en quatre couleurs (pastille blanche sur les boutons pleins).
class GoogleMark extends StatelessWidget {
  const GoogleMark({super.key, this.size = 24, this.badge = true});
  final double size;
  final bool badge;

  @override
  Widget build(BuildContext context) {
    final mark = CustomPaint(size: Size.square(badge ? size * 0.64 : size), painter: _GooglePainter());
    if (!badge) return mark;
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
      alignment: Alignment.center,
      child: mark,
    );
  }
}

class _GooglePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width * 0.2;
    final r = (size.width - w) / 2;
    final c = size.center(Offset.zero);
    final rect = Rect.fromCircle(center: c, radius: r);
    double rad(double d) => d * math.pi / 180;
    void arc(Color color, double start, double sweep) => canvas.drawArc(
      rect,
      rad(start),
      rad(sweep),
      false,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = w,
    );
    arc(const Color(0xFFEA4335), -140, 95); // rouge, en haut
    arc(const Color(0xFFFBBC05), 145, 75); // jaune, à gauche
    arc(const Color(0xFF34A853), 40, 105); // vert, en bas
    arc(const Color(0xFF4285F4), -8, 48); // bleu, à droite
    canvas.drawRect(
      Rect.fromLTWH(c.dx, c.dy - w / 2, r + w / 2, w),
      Paint()..color = const Color(0xFF4285F4),
    );
  }

  @override
  bool shouldRepaint(_GooglePainter old) => false;
}

/// Lien vers une page légale du serveur (ouverte dans le navigateur).
class _LegalLink extends StatelessWidget {
  const _LegalLink(this.text, this.path);
  final String text;
  final String path;

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return GestureDetector(
      onTap: () => state.openUrl(Uri.parse(state.api.baseUrl).resolve(path)),
      child: Text(
        text,
        style: Fp.body(
          12,
          color: Fp.accentLight,
          weight: FontWeight.w700,
          height: 1.4,
        ).copyWith(decoration: TextDecoration.underline),
      ),
    );
  }
}
