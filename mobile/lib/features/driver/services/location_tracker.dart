import 'dart:async';

import 'package:geolocator/geolocator.dart';

import '../../../core/config.dart';
import '../../../core/repository/app_repository.dart';
import '../../../core/storage/app_storage.dart';

/// Emits one freshly-read GPS fix each tick.
class GpsFix {
  const GpsFix({
    required this.lat,
    required this.lng,
    this.speedKmh,
    this.heading,
    required this.ts,
  });

  final double lat;
  final double lng;
  final double? speedKmh;
  final double? heading;
  final DateTime ts;
}

/// Streams GPS fixes at an adaptive cadence (5s moving, 15s stopped) and
/// uploads them to the backend with an offline buffer.
///
/// The cadence adapts to the reported speed to conserve battery. Fixes that
/// cannot be sent are buffered locally (SharedPreferences) and flushed on
/// the next tick, so a dead spot never loses the trail.
class LocationTracker {
  LocationTracker({required AppRepository repo}) : _repo = repo;

  final AppRepository _repo;

  Timer? _timer;
  int? _tripId;
  Duration _interval = AppConfig.movingInterval;
  int _sentCount = 0;

  int get sentCount => _sentCount;
  bool get running => _timer != null;

  void Function(int sentCount)? onSent;
  void Function(String message)? onError;

  Future<void> start({required int tripId}) async {
    await stop();
    _tripId = tripId;
    _sentCount = 0;
    _interval = AppConfig.movingInterval;
    // Flush anything buffered from a previous session for the same trip.
    await _flushBuffer(tripId);
    _scheduleNext();
  }

  Future<void> stop() async {
    _timer?.cancel();
    _timer = null;
    _tripId = null;
  }

  void _scheduleNext() {
    _timer?.cancel();
    _timer = Timer(_interval, () => _tick());
  }

  Future<void> _tick() async {
    final tripId = _tripId;
    if (tripId == null) return;
    try {
      final fix = await _readFix();
      if (fix != null) {
        final accepted = await _trySend(tripId, fix);
        if (accepted) {
          _sentCount++;
          onSent?.call(_sentCount);
        } else {
          await OfflineBuffer.add(BufferedFix(
            tripId: tripId,
            lat: fix.lat,
            lng: fix.lng,
            speedKmh: fix.speedKmh,
            heading: fix.heading,
            ts: fix.ts,
          ).toJson());
        }
        _adaptInterval(fix.speedKmh);
      }
    } catch (e) {
      onError?.call(e.toString());
    }
    _scheduleNext();
  }

  Future<GpsFix?> _readFix() async {
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      return GpsFix(
        lat: pos.latitude,
        lng: pos.longitude,
        speedKmh: pos.speed.isNaN ? null : pos.speed * 3.6,
        heading: pos.heading.isNaN ? null : pos.heading,
        ts: DateTime.now(),
      );
    } catch (_) {
      return null;
    }
  }

  Future<bool> _trySend(int tripId, GpsFix fix) async {
    try {
      return await _repo.sendLocation(
        tripId: tripId,
        lat: fix.lat,
        lng: fix.lng,
        speedKmh: fix.speedKmh,
        heading: fix.heading,
        ts: fix.ts,
      );
    } catch (_) {
      return false;
    }
  }

  Future<void> _flushBuffer(int tripId) async {
    final items = await OfflineBuffer.read();
    if (items.isEmpty) return;
    final pending = <Map<String, dynamic>>[];
    for (final item in items) {
      final buffered = BufferedFix.fromJson(item);
      if (buffered.tripId != tripId) {
        pending.add(item);
        continue;
      }
      try {
        await _repo.sendLocation(
          tripId: tripId,
          lat: buffered.lat,
          lng: buffered.lng,
          speedKmh: buffered.speedKmh,
          heading: buffered.heading,
          ts: buffered.ts,
        );
      } catch (_) {
        pending.add(item);
      }
    }
    await OfflineBuffer.replace(pending);
  }

  void _adaptInterval(double? speedKmh) {
    final moving = (speedKmh ?? 0) > AppConfig.stoppedSpeedKmh;
    final target =
        moving ? AppConfig.movingInterval : AppConfig.stoppedInterval;
    if (target != _interval) {
      _interval = target;
    }
  }
}
