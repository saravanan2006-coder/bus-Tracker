import 'package:flutter/foundation.dart';

import '../../../core/models/models.dart';
import '../../../core/repository/app_repository.dart';
import '../services/location_tracker.dart';

/// Driver home state: buses, active trip and location streaming.
class DriverController extends ChangeNotifier {
  DriverController(this._repo) : tracker = LocationTracker(repo: _repo);

  final AppRepository _repo;
  final LocationTracker tracker;

  List<Bus> _buses = [];
  Trip? _activeTrip;
  bool _loadingBuses = false;
  bool _startingTrip = false;
  String? _error;

  List<Bus> get buses => _buses;
  Trip? get activeTrip => _activeTrip;
  bool get loadingBuses => _loadingBuses;
  bool get startingTrip => _startingTrip;
  String? get error => _error;

  Future<void> load() async {
    await Future.wait([loadBuses(), loadActiveTrip()]);
  }

  Future<void> loadBuses() async {
    _loadingBuses = true;
    _error = null;
    notifyListeners();
    try {
      _buses = await _repo.myBuses();
    } catch (e) {
      _error = e.toString();
    } finally {
      _loadingBuses = false;
      notifyListeners();
    }
  }

  Future<void> loadActiveTrip() async {
    try {
      _activeTrip = await _repo.activeTrip();
      if (_activeTrip != null) {
        await tracker.start(tripId: _activeTrip!.id);
      }
    } catch (_) {
      // Best-effort restore.
    }
    notifyListeners();
  }

  Future<bool> registerBus({
    required String busNumber,
    required String rtoNumber,
    required String busType,
    String? busName,
  }) async {
    _error = null;
    notifyListeners();
    try {
      await _repo.registerBus(
        busNumber: busNumber,
        rtoNumber: rtoNumber,
        busType: busType,
        busName: busName,
      );
      await loadBuses();
      return true;
    } catch (e) {
      _error = e.toString();
      notifyListeners();
      return false;
    }
  }

  Future<bool> startTrip({required int busId, required int routeId}) async {
    _startingTrip = true;
    _error = null;
    notifyListeners();
    try {
      final trip = await _repo.startTrip(busId: busId, routeId: routeId);
      _activeTrip = trip;
      await tracker.start(tripId: trip.id);
      return true;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _startingTrip = false;
      notifyListeners();
    }
  }

  Future<bool> endTrip() async {
    final trip = _activeTrip;
    if (trip == null) return false;
    await tracker.stop();
    try {
      await _repo.endTrip(trip.id);
    } finally {
      _activeTrip = null;
      notifyListeners();
    }
    return true;
  }
}
