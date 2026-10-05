import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../state/app_state.dart';
import '../theme.dart';
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

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool register = false;
  bool busy = false;
  bool adult = false;
  bool showPassword = false;
  String country = 'BJ';
  String? error;
  final phone = TextEditingController(text: '+229 ');
  final password = TextEditingController();
  final name = TextEditingController();

  @override
  void dispose() {
    phone.dispose();
    password.dispose();
    name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final state = context.read<AppState>();
    setState(() {
      busy = true;
      error = null;
    });
    try {
      if (register) {
        if (!adult) throw ApiException(400, 'adult', 'Il faut avoir 18 ans ou plus pour utiliser FootProba.');
        await state.register(
          phone: phone.text,
          password: password.text,
          name: name.text.trim(),
          country: country,
          adult: adult,
        );
      } else {
        await state.login(phone.text, password.text);
      }
    } on ApiException catch (e) {
      setState(() => error = e.message);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 30, 20, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Align(alignment: Alignment.centerLeft, child: FpLogo(size: 20)),
                  const SizedBox(height: 26),
                  GlassCard.main(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        register
                            ? const TwoToneTitle('Créer un', 'compte', size: 26)
                            : const TwoToneTitle('Bon', 'retour', size: 26),
                        const SizedBox(height: 6),
                        Text(
                          register
                              ? 'Rejoins FootProba et suis tes pronostics en temps réel.'
                              : 'Connecte-toi pour retrouver tes pronostics, coupons et montantes.',
                          style: Fp.body(14, color: Fp.text2, height: 1.4),
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
                          Text(
                            'Pays',
                            style: Fp.body(13, weight: FontWeight.w600, color: Fp.textStrong),
                          ),
                          const SizedBox(height: 7),
                          DropdownButtonFormField<String>(
                            isExpanded: true,
                            initialValue: country,
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
                            onChanged: (v) => setState(() {
                              final old = dialCodes[country]!;
                              country = v ?? country;
                              if (phone.text.trim().isEmpty || phone.text.trim() == old) {
                                phone.text = '${dialCodes[country]} ';
                              }
                            }),
                          ),
                          const SizedBox(height: 14),
                        ],
                        FpField(
                          label: 'Numéro de téléphone',
                          controller: phone,
                          icon: Icons.phone_iphone_rounded,
                          hint: '+229 97 00 00 00',
                          keyboardType: TextInputType.phone,
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
                            icon: Icon(
                              showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                            ),
                            onPressed: () => setState(() => showPassword = !showPassword),
                          ),
                        ),
                        if (register) ...[
                          const SizedBox(height: 14),
                          InkWell(
                            onTap: () => setState(() => adult = !adult),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: Checkbox(
                                    value: adult,
                                    onChanged: (v) => setState(() => adult = v ?? false),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    "J'ai 18 ans ou plus",
                                    style: Fp.body(13, color: Fp.textStrong, height: 1.4),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            'Argent fictif uniquement : aucun pari réel. 7 jours de Premium offerts.',
                            style: Fp.body(12, color: Fp.accentLight, weight: FontWeight.w600, height: 1.4),
                          ),
                          const SizedBox(height: 8),
                          Wrap(
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              Text(
                                'En créant un compte, tu acceptes les ',
                                style: Fp.body(12, color: Fp.text2, height: 1.4),
                              ),
                              _LegalLink('conditions d\'utilisation', '/conditions'),
                              Text(' et la ', style: Fp.body(12, color: Fp.text2, height: 1.4)),
                              _LegalLink('politique de confidentialité', '/confidentialite'),
                              Text('.', style: Fp.body(12, color: Fp.text2, height: 1.4)),
                            ],
                          ),
                        ],
                        if (error != null) ...[
                          const SizedBox(height: 14),
                          Text(error!, style: Fp.body(13, color: Fp.lossText, height: 1.4)),
                        ],
                        const SizedBox(height: 20),
                        FilledButton(
                          onPressed: busy ? null : _submit,
                          child: busy
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(register ? 'Créer mon compte' : 'Se connecter'),
                                    const SizedBox(width: 10),
                                    const Icon(Icons.arrow_forward_rounded, size: 20),
                                  ],
                                ),
                        ),
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
                                onTap: busy
                                    ? null
                                    : () => setState(() {
                                        register = !register;
                                        error = null;
                                      }),
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
