import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/geo.dart';
import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/empty_view.dart';
import '../../../shared_widgets/error_view.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../../../shared_widgets/status_banner.dart';
import '../controllers/public_controller.dart';
import 'bus_map_screen.dart';

/// Step 3: routes between the chosen villages, with live buses.
class RouteResultsScreen extends StatelessWidget {
  const RouteResultsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('busesFound'))),
      body: SafeArea(
        child: controller.loadingResults
            ? const LoadingIndicator()
            : controller.error != null
                ? ErrorView(
                    message: controller.error!,
                    onRetry: controller.loadDistricts,
                  )
                : controller.results.isEmpty
                    ? EmptyView(
                        icon: Icons.directions_bus_outlined,
                        caption: loc.t('noBusesNow'),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: controller.results.length,
                        itemBuilder: (context, index) {
                          final result = controller.results[index];
                          return _RouteCard(result: result);
                        },
                      ),
      ),
    );
  }
}

class _RouteCard extends StatelessWidget {
  const _RouteCard({required this.result});

  final RouteWithBuses result;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final buses = result.buses;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.route, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${result.route.distanceM != null ? Format.distance(result.route.distanceM!) : ''}'
                    ' · ${loc.t('routeActive')}',
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            if (buses.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(loc.t('noBusesNow')),
              )
            else
              ...buses.map(
                (bus) => Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: _BusTile(bus: bus, routePolyline: result.route.polyline),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _BusTile extends StatelessWidget {
  const _BusTile({required this.bus, required this.routePolyline});

  final BusDetail bus;
  final List<List<double>> routePolyline;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final live = bus.live;
    final eta = bus.eta;

    final bool isLive = live != null && !live.ended && !live.stale;
    final bool stale = live != null && live.stale && !live.ended;

    return InkWell(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => BusMapScreen(
            bus: bus,
            routePolyline: routePolyline,
          ),
        ),
      ),
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: Theme.of(context).colorScheme.surface,
          border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        ),
        child: Row(
          children: [
            CircleAvatar(
              backgroundColor: isLive
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).colorScheme.surfaceContainerHighest,
              child: Icon(
                Icons.directions_bus,
                color: isLive
                    ? Theme.of(context).colorScheme.onPrimary
                    : Theme.of(context).colorScheme.outline,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        bus.busNumber,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w800),
                      ),
                      if (bus.busName != null && bus.busName!.isNotEmpty) ...[
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            bus.busName!,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                color: Theme.of(context)
                                    .colorScheme
                                    .onSurfaceVariant),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 6),
                  if (eta != null && isLive)
                    Text(
                      '${loc.t('etaMinutes', args: {'m': Format.etaMinutes(eta.etaMinutes)})}'
                      ' · ${Format.distance(eta.distanceRemainingM)}',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                        fontWeight: FontWeight.w700,
                      ),
                    )
                  else if (stale)
                    Text(loc.t('stale'),
                        style: TextStyle(
                            color: Theme.of(context).colorScheme.error)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            if (isLive)
              StatusBanner(
                color: Theme.of(context).colorScheme.primary,
                icon: Icons.circle,
                text: loc.t('live'),
              )
            else if (live != null && live.ended)
              StatusBanner(
                color: Theme.of(context).colorScheme.outline,
                icon: Icons.stop_circle_outlined,
                text: loc.t('tripEnded'),
              )
            else
              StatusBanner(
                color: Theme.of(context).colorScheme.outline,
                icon: Icons.cloud_off,
                text: loc.t('offlineBus'),
              ),
          ],
        ),
      ),
    );
  }
}
