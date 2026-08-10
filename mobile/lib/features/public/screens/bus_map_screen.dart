import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../../core/geo.dart';
import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../core/push/push_service.dart';
import '../../../core/repository/app_repository.dart';
import '../../../core/storage/app_storage.dart';
import '../../../core/websocket/bus_ws_client.dart';
import '../../../shared_widgets/status_banner.dart';

/// Full live view for a single bus: map + route + stops + live marker.
///
/// [routePolyline] is provided by the results screen; otherwise the route is
/// fetched from the backend. Stop markers are derived by projecting each
/// stop's progress value onto the route polyline.
class BusMapScreen extends StatefulWidget {
  const BusMapScreen({
    super.key,
    required this.bus,
    this.routePolyline,
  });

  final BusDetail bus;
  final List<List<double>>? routePolyline;

  @override
  State<BusMapScreen> createState() => _BusMapScreenState();
}

class _BusMapScreenState extends State<BusMapScreen> {
  final _mapController = MapController();

  BusWsClient? _ws;
  Timer? _reconnectTimer;
  bool _disposed = false;
  bool _favoriteSaving = false;

  BusDetail? _bus;
  List<LatLng> _trail = [];
  List<LatLng> _polyline = [];

  BusDetail get bus => _bus ?? widget.bus;

  @override
  void initState() {
    super.initState();
    _bus = widget.bus;
    _polyline = (widget.routePolyline ?? [])
        .where((p) => p.length >= 2)
        .map((p) => LatLng(p[0], p[1]))
        .toList();
    _connect();
    _loadDetail();
  }

  @override
  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _ws?.disconnect();
    _mapController.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------------ //
  // Live feed
  // ------------------------------------------------------------------ //
  Future<void> _connect() async {
    final client = BusWsClient(widget.bus.id);
    _ws = client;
    await client.connect();
    if (_disposed) return;
    client.positions.listen(_onLive, onDone: _onWsClosed, onError: (_) => _onWsClosed());
  }

  void _onWsClosed() {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 4), _connect);
  }

  void _onLive(LivePosition pos) {
    if (_disposed) return;
    setState(() {
      _bus = BusDetail(
        id: bus.id,
        busNumber: bus.busNumber,
        busName: bus.busName,
        busType: bus.busType,
        rtoNumber: bus.rtoNumber,
        verified: bus.verified,
        route: bus.route,
        live: pos,
        eta: bus.eta,
      );
    });
  }

  // ------------------------------------------------------------------ //
  // Static data (route geometry + history trail)
  // ------------------------------------------------------------------ //
  Future<void> _loadDetail() async {
    final repo = context.read<AppRepository>();
    try {
      final detail = await repo.busDetail(widget.bus.id);
      if (_disposed) return;
      setState(() => _bus = detail);

      if (_polyline.isEmpty && detail.route != null) {
        try {
          final routeInfo = await repo.route(detail.route!.id);
          if (_disposed) return;
          setState(() {
            _polyline = routeInfo.polyline
                .where((p) => p.length >= 2)
                .map((p) => LatLng(p[0], p[1]))
                .toList();
          });
        } catch (_) {
          // Geometry is best-effort; the live marker still renders.
        }
      }

      final history = await repo.busHistory(widget.bus.id);
      if (_disposed) return;
      setState(() {
        _trail = history
            .map((p) => LatLng(
                  (p['lat'] as num).toDouble(),
                  (p['lng'] as num).toDouble(),
                ))
            .toList();
      });
      _fitInitialCamera();
    } catch (_) {
      // Live feed still works without static detail.
    }
  }

  LatLng? _stopPosition(StopSummary stop) {
    if (_polyline.isEmpty) return null;
    final progress = stop.progress.clamp(0.0, 1.0);
    return _pointAtProgress(_polyline, progress);
  }

  LatLng _pointAtProgress(List<LatLng> line, double progress) {
    final total = _pathLength(line);
    if (total <= 0) return line.first;
    final target = total * progress;
    var walked = 0.0;
    for (var i = 0; i < line.length - 1; i++) {
      final segLen =
          const Distance().as(LengthUnit.Meter, line[i], line[i + 1]);
      if (walked + segLen >= target) {
        final t = segLen == 0 ? 0.0 : (target - walked) / segLen;
        return LatLng(
          line[i].latitude + (line[i + 1].latitude - line[i].latitude) * t,
          line[i].longitude + (line[i + 1].longitude - line[i].longitude) * t,
        );
      }
      walked += segLen;
    }
    return line.last;
  }

  double _pathLength(List<LatLng> line) {
    var total = 0.0;
    for (var i = 0; i < line.length - 1; i++) {
      total += const Distance().as(LengthUnit.Meter, line[i], line[i + 1]);
    }
    return total;
  }

  void _fitInitialCamera() {
    final live = bus.live;
    final points = <LatLng>[
      if (live != null && live.hasPosition) LatLng(live.lat!, live.lng!),
      ..._polyline,
    ];
    if (points.isEmpty) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_disposed) return;
      _mapController.fitCamera(
        CameraFit.bounds(
          bounds: LatLngBounds.fromPoints(points),
          padding: const EdgeInsets.all(48),
        ),
      );
    });
  }

  void _follow() {
    final live = bus.live;
    if (live == null || !live.hasPosition) return;
    _mapController.move(LatLng(live.lat!, live.lng!), 14);
  }

  // ------------------------------------------------------------------ //
  // Actions
  // ------------------------------------------------------------------ //
  Future<void> _saveFavorite() async {
    final loc = context.read<LocalizationController>();
    final repo = context.read<AppRepository>();
    final route = bus.route;
    if (route == null || route.fromVillage == null || route.toVillage == null) {
      return;
    }
    setState(() => _favoriteSaving = true);
    try {
      await repo.addFavorite(
        deviceId: await AppStorage.deviceId(),
        fromVillageId: route.fromVillage!.id,
        toVillageId: route.toVillage!.id,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('favoriteAdded'))),
      );
    } finally {
      if (!_disposed) setState(() => _favoriteSaving = false);
    }
  }

  Future<void> _subscribeAlert() async {
    final loc = context.read<LocalizationController>();
    final repo = context.read<AppRepository>();
    final nextStop = bus.eta?.nextStop ?? bus.route?.stops.firstOrNull;
    if (nextStop == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('alertUnavailable'))),
      );
      return;
    }
    final token = await PushService.obtainToken();
    if (!mounted) return;
    if (token == null) {
      // Firebase not configured or permission denied: nothing to notify.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('alertUnavailable'))),
      );
      return;
    }
    try {
      await repo.subscribeAlert(
        deviceId: await AppStorage.deviceId(),
        busId: bus.id,
        stopVillageId: nextStop.villageId,
        fcmToken: token,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('alertSubscribed'))),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('alertUnavailable'))),
      );
    }
  }

  // ------------------------------------------------------------------ //
  // UI
  // ------------------------------------------------------------------ //
  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final live = bus.live;
    final isLive = live != null && !live.ended && !live.stale;

    return Scaffold(
      appBar: AppBar(
        title: Text(
            '${bus.busNumber}${bus.busName != null && bus.busName!.isNotEmpty ? ' · ${bus.busName}' : ''}'),
        actions: [
          IconButton(
            tooltip: loc.t('addFavorite'),
            onPressed: _favoriteSaving ? null : _saveFavorite,
            icon: const Icon(Icons.star_border),
          ),
          IconButton(
            tooltip: loc.t('alertMe'),
            onPressed: _subscribeAlert,
            icon: const Icon(Icons.notifications_none),
          ),
        ],
      ),
      body: Stack(
        children: [
          _buildMap(),
          Positioned(
            top: 12,
            left: 12,
            child: isLive
                ? StatusBanner(
                    color: Theme.of(context).colorScheme.primary,
                    icon: Icons.circle,
                    text: loc.t('liveNow'),
                  )
                : StatusBanner(
                    color: Theme.of(context).colorScheme.error,
                    icon: Icons.cloud_off,
                    text: live != null && live.ended
                        ? loc.t('tripEnded')
                        : loc.t('stale'),
                  ),
          ),
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: _BottomSheet(
              bus: bus,
              isLive: isLive,
              onFollow: _follow,
              stopPosition: _stopPosition,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMap() {
    final live = bus.live;
    final markers = <Marker>[
      if (live != null && live.hasPosition)
        Marker(
          point: LatLng(live.lat!, live.lng!),
          width: 46,
          height: 46,
          child: const _BusMarker(),
        ),
    ];
    for (final stop in bus.route?.stops ?? <StopSummary>[]) {
      final pos = _stopPosition(stop);
      if (pos == null) continue;
      markers.add(
        Marker(point: pos, width: 24, height: 24, child: const _StopMarker()),
      );
    }
    for (final point in _trail) {
      markers.add(
        Marker(
          point: point,
          width: 9,
          height: 9,
          child: DecoratedBox(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Theme.of(context)
                  .colorScheme
                  .primary
                  .withValues(alpha: 0.45),
            ),
          ),
        ),
      );
    }

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: live != null && live.hasPosition
            ? LatLng(live.lat!, live.lng!)
            : const LatLng(11.9, 79.5),
        initialZoom: 13,
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'in.bustracker.app',
        ),
        if (_polyline.length >= 2)
          PolylineLayer(
            polylines: [
              Polyline(
                points: _polyline,
                strokeWidth: 5,
                color: Theme.of(context).colorScheme.primary,
              ),
            ],
          ),
        if (_trail.length >= 2)
          PolylineLayer(
            polylines: [
              Polyline(
                points: _trail,
                strokeWidth: 3,
                color: Theme.of(context).colorScheme.tertiary,
              ),
            ],
          ),
        MarkerLayer(markers: markers),
        RichAttributionWidget(
          attributions: const [
            TextSourceAttribution('OpenStreetMap contributors'),
          ],
        ),
      ],
    );
  }
}

class _BusMarker extends StatelessWidget {
  const _BusMarker();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primary,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: const [
          BoxShadow(color: Colors.black26, blurRadius: 6, offset: Offset(0, 2)),
        ],
      ),
      child: const Icon(Icons.directions_bus, color: Colors.white, size: 26),
    );
  }
}

class _StopMarker extends StatelessWidget {
  const _StopMarker();

  @override
  Widget build(BuildContext context) {
    return Icon(Icons.place, color: Theme.of(context).colorScheme.error);
  }
}

class _BottomSheet extends StatelessWidget {
  const _BottomSheet({
    required this.bus,
    required this.isLive,
    required this.onFollow,
    required this.stopPosition,
  });

  final BusDetail bus;
  final bool isLive;
  final VoidCallback onFollow;
  final LatLng? Function(StopSummary stop) stopPosition;

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final live = bus.live;
    final eta = bus.eta;
    final route = bus.route;
    final from = route?.fromVillage;
    final to = route?.toVillage;

    return Material(
      elevation: 12,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.outlineVariant,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${from?.name ?? '?'}  →  ${to?.name ?? '?'}',
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w800),
                        ),
                        if (eta != null && isLive) ...[
                          const SizedBox(height: 6),
                          Text(
                            '${loc.t('eta')}: ${loc.t('etaMinutes', args: {'m': Format.etaMinutes(eta.etaMinutes)})}',
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontWeight: FontWeight.w700,
                              fontSize: 15,
                            ),
                          ),
                          Text(
                            Format.distance(eta.distanceRemainingM),
                            style: TextStyle(
                                color: Theme.of(context)
                                    .colorScheme
                                    .onSurfaceVariant),
                          ),
                        ],
                      ],
                    ),
                  ),
                  IconButton.filledTonal(
                    onPressed: onFollow,
                    icon: const Icon(Icons.my_location),
                    tooltip: loc.t('follow'),
                  ),
                ],
              ),
              if (live != null && !live.ended && live.speedKmh != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(
                    loc.t('speed', args: {'s': live.speedKmh!.round().toString()}),
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant),
                  ),
                ),
              if (route != null && route.stops.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: _StopsStrip(
                    stops: route.stops,
                    activeProgress: eta?.progress ?? 0,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StopsStrip extends StatelessWidget {
  const _StopsStrip({required this.stops, required this.activeProgress});

  final List<StopSummary> stops;
  final double activeProgress;

  @override
  Widget build(BuildContext context) {
    final sorted = [...stops]..sort((a, b) => a.seq.compareTo(b.seq));
    final shown = sorted.length > 7 ? sorted.sublist(0, 7) : sorted;

    return SizedBox(
      height: 40,
      child: Row(
        children: [
          for (var i = 0; i < shown.length; i++)
            Expanded(
              child: _StopChip(
                stop: shown[i],
                passed: shown[i].progress < activeProgress - 0.001,
                isLast: i == shown.length - 1,
              ),
            ),
        ],
      ),
    );
  }
}

class _StopChip extends StatelessWidget {
  const _StopChip({
    required this.stop,
    required this.passed,
    required this.isLast,
  });

  final StopSummary stop;
  final bool passed;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final color = passed
        ? Theme.of(context).colorScheme.outline
        : Theme.of(context).colorScheme.primary;
    return Row(
      children: [
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.circle, size: 10, color: color),
              const SizedBox(height: 2),
              Text(
                stop.village?.name ?? '',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 10, color: color),
              ),
            ],
          ),
        ),
        if (!isLast)
          Expanded(
            child: Container(height: 2, color: color.withValues(alpha: 0.4)),
          ),
      ],
    );
  }
}
