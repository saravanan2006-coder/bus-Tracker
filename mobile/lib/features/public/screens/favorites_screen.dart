import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/empty_view.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../controllers/public_controller.dart';

/// Saved village pairs, listed for one-tap re-search.
class FavoritesScreen extends StatelessWidget {
  const FavoritesScreen({super.key, required this.onOpenPair});

  final void Function(int fromVillageId, int toVillageId) onOpenPair;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();

    if (controller.loadingFavorites) return const LoadingIndicator();

    if (controller.favorites.isEmpty) {
      return EmptyView(
        icon: Icons.star_border,
        caption: loc.t('noFavorites'),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: controller.favorites.length,
      itemBuilder: (context, index) {
        final favorite = controller.favorites[index];
        final from = controller.favoriteDetails
            .where((v) => v.id == favorite.fromVillageId)
            .firstOrNull;
        final to = controller.favoriteDetails
            .where((v) => v.id == favorite.toVillageId)
            .firstOrNull;
        final fromName = _name(loc, from);
        final toName = _name(loc, to);

        return Card(
          margin: const EdgeInsets.only(bottom: 10),
          child: ListTile(
            leading: const Icon(Icons.star, color: Colors.amber),
            title: Text(
              '$fromName  →  $toName',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: loc.t('removeFavorite'),
              onPressed: () => controller.removeFavorite(favorite),
            ),
            onTap: from != null && to != null
                ? () => onOpenPair(from.id, to.id)
                : null,
          ),
        );
      },
    );
  }

  String _name(LocalizationController loc, Village? v) {
    if (v == null) return '?';
    return loc.language == 'ta' && v.nameTa != null ? v.nameTa! : v.name;
  }
}
