import 'package:flutter/material.dart';

/// Empty-state placeholder with an icon and caption.
class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.icon, required this.caption});

  final IconData icon;
  final String caption;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 56, color: Theme.of(context).colorScheme.outline),
            const SizedBox(height: 12),
            Text(caption, textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}
