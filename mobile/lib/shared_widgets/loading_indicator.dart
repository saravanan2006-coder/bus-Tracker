import 'package:flutter/material.dart';

/// Centered spinner with an optional caption.
class LoadingIndicator extends StatelessWidget {
  const LoadingIndicator({super.key, this.caption});

  final String? caption;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(),
          if (caption != null) ...[
            const SizedBox(height: 12),
            Text(caption!, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ],
      ),
    );
  }
}
