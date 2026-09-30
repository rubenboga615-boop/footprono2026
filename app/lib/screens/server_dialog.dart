import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../state/app_state.dart';
import '../theme.dart';

/// Adresse du serveur FootProno (Termux sur ce téléphone par défaut).
Future<void> showServerDialog(BuildContext context) async {
  final state = context.read<AppState>();
  final controller = TextEditingController(text: state.api.baseUrl);
  String? result;
  await showDialog<void>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        title: const Text('Adresse du serveur'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Serveur Termux sur ce téléphone : http://127.0.0.1:8000\n'
              'Depuis un autre appareil du même Wi-Fi : http://<adresse du téléphone>:8000',
            ),
            const SizedBox(height: 14),
            TextField(controller: controller, keyboardType: TextInputType.url, autocorrect: false),
            if (result != null) ...[
              const SizedBox(height: 10),
              Text(result!, style: Fp.body(13, color: result!.startsWith('OK') ? Fp.win : Fp.loss)),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () async {
              final probe = ApiClient(baseUrl: controller.text.trim());
              try {
                final r = await probe.get('/ready') as Map;
                setState(
                  () => result = r['status'] == 'ready' ? 'OK : serveur prêt' : 'Serveur joint mais pas prêt',
                );
              } on ApiException catch (e) {
                setState(() => result = e.message);
              }
            },
            child: const Text('Tester'),
          ),
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(0, 40)),
            onPressed: () async {
              Navigator.pop(context);
              try {
                await state.setServer(controller.text);
                showMessage('Serveur enregistré');
              } on ApiException catch (e) {
                showMessage(e.message, error: true);
              }
            },
            child: const Text('Enregistrer'),
          ),
        ],
      ),
    ),
  );
}
