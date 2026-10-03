// Outils de mise en page partagés entre la version téléphone et la version ordinateur.
import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../widgets/common.dart';

/// Largeur de fenêtre à partir de laquelle l'application prend sa disposition d'ordinateur.
const desktopMinWidth = 1100.0;

/// Marqueur posé autour de la zone centrale de la version ordinateur.
class DesktopScope extends InheritedWidget {
  const DesktopScope({super.key, required super.child});

  static bool of(BuildContext context) => context.getInheritedWidgetOfExactType<DesktopScope>() != null;

  @override
  bool updateShouldNotify(DesktopScope oldWidget) => false;
}

/// Marges d'une page : sur téléphone 18 px ; sur ordinateur, le contenu est centré dans
/// [maxWidth] et n'a plus à laisser la place de la barre de navigation flottante.
EdgeInsets pagePadding(BuildContext context, double top, double bottom, {double maxWidth = 760}) {
  if (!DesktopScope.of(context)) return EdgeInsets.fromLTRB(18, top, 18, bottom);
  final side = math.max(28.0, (MediaQuery.sizeOf(context).width - maxWidth) / 2);
  return EdgeInsets.fromLTRB(side, math.max(top, 22), side, math.min(bottom, 40));
}

/// Version ordinateur : une liste de cartes devient deux colonnes côte à côte
/// (coupées vers le milieu, jamais juste après un titre). Sur téléphone, rien ne change.
List<Widget> deskColumns(BuildContext context, List<Widget> items, {double minWidth = 860}) {
  if (!DesktopScope.of(context) || MediaQuery.sizeOf(context).width < minWidth || items.length < 2) {
    return items;
  }
  int weight(Widget w) => w is SizedBox ? 0 : (w is Padding || w is Text ? 1 : 3);
  bool heading(Widget w) => w is SizedBox || w is Text || w is SectionTitle;
  final total = items.fold<int>(0, (t, w) => t + weight(w));
  var best = -1, bestGap = 1 << 30, acc = 0;
  for (var i = 1; i < items.length; i++) {
    acc += weight(items[i - 1]);
    if (heading(items[i - 1])) continue;
    final gap = (2 * acc - total).abs();
    if (gap < bestGap) {
      bestGap = gap;
      best = i;
    }
  }
  if (best <= 0) return items;
  List<Widget> trim(List<Widget> l) {
    final out = [...l];
    while (out.isNotEmpty && out.first is SizedBox) {
      out.removeAt(0);
    }
    return out;
  }

  return [
    Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: trim(items.sublist(0, best)),
          ),
        ),
        const SizedBox(width: 18),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: trim(items.sublist(best))),
        ),
      ],
    ),
  ];
}

/// Version ordinateur : réglages dans une colonne étroite à gauche, résultat à droite.
/// Sur téléphone, les deux listes se suivent.
List<Widget> deskSplit(
  BuildContext context,
  List<Widget> left,
  List<Widget> right, {
  double leftWidth = 400,
  double minWidth = 860,
}) {
  if (!DesktopScope.of(context) || MediaQuery.sizeOf(context).width < minWidth) return [...left, ...right];
  return [
    Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: leftWidth,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: left),
        ),
        const SizedBox(width: 28),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final w in right)
                if (w is! SizedBox || right.first != w) w,
            ],
          ),
        ),
      ],
    ),
  ];
}
