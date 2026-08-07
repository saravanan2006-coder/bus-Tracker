import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/status_banner.dart';
import '../controllers/driver_controller.dart';
import '../services/foreground_service.dart';

/// Live "sharing" screen for an active trip: big stop button, update counter
/// and a background-service keepalive notice.
class TripScreen extends StatefulWidget {
  const TripScreen({super.key, required this.trip, required this.bus});

  final Trip trip;
  final Bus bus;

  @override
  State<TripScreen> createState() => _TripScreenState();
}

class _TripScreenState extends State<TripScreen> {
  bool _ending = false;
  int _sent = 0;
  Timer? _uiTicker;
  Duration _elapsed = Duration.zero;

  @override
  void initState() {
    super.initState();
    final controller = context.read<DriverController>();
    controller.tracker.onSent = (count) {
      if (mounted) setState(() => _sent = count);
    };
    _sent = controller.tracker.sentCount;
    _uiTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {
          _elapsed = DateTime.now().difference(widget.trip.startedAt);
        });
      }
    });
    ForegroundService.start(
      title: widget.bus.busNumber,
      text: 'Location sharing is active',
    );
  }

  @override
  void dispose() {
    _uiTicker?.cancel();
    super.dispose();
  }

  Future<void> _endTrip() async {
    final loc = context.read<LocalizationController>();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(loc.t('endTrip')),
        content: Text(loc.t('endTripConfirm')),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(loc.t('cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(loc.t('endTrip')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _ending = true);
    final controller = context.read<DriverController>();
    await controller.endTrip();
    await ForegroundService.stop();
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  String _formatElapsed(Duration d) {
    final h = d.inHours.toString().padLeft(2, '0');
    final m = (d.inMinutes % 60).toString().padLeft(2, '0');
    final s = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.bus.busNumber),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              StatusBanner(
                color: Theme.of(context).colorScheme.primary,
                icon: Icons.circle,
                text: loc.t('sharing'),
              ),
              const Spacer(),
              _BigShareButton(
                onPressed: _ending ? null : _endTrip,
              ),
              const SizedBox(height: 24),
              Text(
                loc.t('pointsSent'),
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
              const SizedBox(height: 4),
              Text(
                '$_sent',
                style: const TextStyle(
                    fontSize: 34, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              Text(
                _formatElapsed(_elapsed),
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant),
              ),
              const Spacer(),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.battery_saver,
                      size: 16,
                      color: Theme.of(context).colorScheme.onSurfaceVariant),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      loc.t('backgroundNotice'),
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BigShareButton extends StatelessWidget {
  const _BigShareButton({required this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.errorContainer,
      shape: const CircleBorder(),
      elevation: 6,
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onPressed,
        child: Container(
          width: 180,
          height: 180,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: scheme.error, width: 4),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.stop_circle, size: 56, color: scheme.error),
              const SizedBox(height: 8),
              Text(
                'STOP',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 2,
                  color: scheme.onErrorContainer,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
