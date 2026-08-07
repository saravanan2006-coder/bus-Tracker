import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/empty_view.dart';
import '../../../shared_widgets/error_view.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../controllers/auth_controller.dart';
import '../controllers/driver_controller.dart';
import 'build_route_screen.dart';
import 'register_bus_screen.dart';
import 'trip_screen.dart';

/// Driver home: buses, active trip banner, add-bus and route actions.
class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({super.key});

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DriverController>().load();
    });
  }

  Future<void> _startTrip(Bus bus) async {
    final loc = context.read<LocalizationController>();
    final controller = context.read<DriverController>();
    final routeId = bus.routeId;
    if (routeId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('noRouteAssigned'))),
      );
      return;
    }
    final ok = await controller.startTrip(busId: bus.id, routeId: routeId);
    if (!mounted) return;
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(controller.error ?? loc.t('error'))),
      );
      return;
    }
    _openTrip();
  }

  void _openTrip() {
    final controller = context.read<DriverController>();
    final trip = controller.activeTrip;
    if (trip == null) return;
    final bus = controller.buses
        .where((b) => b.id == trip.busId)
        .firstOrNull;
    if (bus == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => TripScreen(trip: trip, bus: bus)),
    );
  }

  Future<void> _logout() async {
    final loc = context.read<LocalizationController>();
    final auth = context.read<AuthController>();
    await auth.logout();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(loc.t('loggedOut'))),
    );
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<DriverController>();
    final activeTrip = controller.activeTrip;

    return Scaffold(
      appBar: AppBar(
        title: Text(loc.t('myBuses')),
        actions: [
          IconButton(
            icon: const Icon(Icons.translate),
            tooltip: loc.language == 'ta' ? 'English' : 'தமிழ்',
            onPressed: () => context.read<LocalizationController>().toggle(),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: loc.t('logout'),
            onPressed: _logout,
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const RegisterBusScreen()),
        ),
        icon: const Icon(Icons.add),
        label: Text(loc.t('addBus')),
      ),
      body: SafeArea(
        child: controller.loadingBuses
            ? const LoadingIndicator()
            : controller.error != null
                ? ErrorView(
                    message: controller.error!,
                    onRetry: controller.load,
                  )
                : controller.buses.isEmpty
                    ? EmptyView(
                        icon: Icons.directions_bus_outlined,
                        caption: loc.t('noBusesYet'),
                      )
                    : ListView(
                        padding: const EdgeInsets.only(
                            left: 16, right: 16, top: 16, bottom: 96),
                        children: [
                          if (activeTrip != null)
                            _ActiveTripBanner(onTap: _openTrip),
                          const SizedBox(height: 8),
                          for (final bus in controller.buses)
                            _BusCard(
                              bus: bus,
                              onStartTrip: () => _startTrip(bus),
                              onAssignRoute: () async {
                                final assigned = await Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => BuildRouteScreen(
                                        buses: controller.buses),
                                  ),
                                );
                                if (assigned == true) {
                                  unawaited(controller.loadBuses());
                                }
                              },
                            ),
                        ],
                      ),
      ),
    );
  }
}

class _ActiveTripBanner extends StatelessWidget {
  const _ActiveTripBanner({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.primaryContainer,
      child: ListTile(
        leading: const Icon(Icons.radio_button_checked),
        title: Text(
          loc.t('tripActive'),
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

class _BusCard extends StatelessWidget {
  const _BusCard({
    required this.bus,
    required this.onStartTrip,
    required this.onAssignRoute,
  });

  final Bus bus;
  final VoidCallback onStartTrip;
  final VoidCallback onAssignRoute;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final scheme = Theme.of(context).colorScheme;
    final approved = bus.verificationStatus == 'approved';

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: scheme.surfaceContainerHighest,
                  child: const Icon(Icons.directions_bus),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        bus.busNumber,
                        style: const TextStyle(
                            fontSize: 17, fontWeight: FontWeight.w800),
                      ),
                      if (bus.busName != null && bus.busName!.isNotEmpty)
                        Text(bus.busName!),
                      Text(
                        bus.rtoNumber,
                        style: TextStyle(color: scheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                _VerificationChip(
                  status: bus.verificationStatus,
                  loc: loc,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: approved || bus.routeId != null
                        ? onStartTrip
                        : null,
                    icon: const Icon(Icons.play_arrow),
                    label: Text(loc.t('startSharing')),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: onAssignRoute,
                  icon: const Icon(Icons.route),
                  tooltip: loc.t('buildRoute'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _VerificationChip extends StatelessWidget {
  const _VerificationChip({required this.status, required this.loc});

  final String status;
  final LocalizationController loc;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (color, label) = switch (status) {
      'approved' => (scheme.primary, loc.t('approved')),
      'rejected' => (scheme.error, loc.t('rejected')),
      _ => (scheme.outline, loc.t('pending')),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 12),
      ),
    );
  }
}
