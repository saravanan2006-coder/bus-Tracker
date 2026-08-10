import 'package:flutter/foundation.dart';

import '../../../core/geo/detector.dart';
import '../../../core/models/models.dart';
import '../../../core/repository/app_repository.dart';
import '../../../core/storage/app_storage.dart';

/// State for the passenger side: districts, village search, route results
/// and favourites. All guest (no login).
class PublicController extends ChangeNotifier {
  PublicController(this._repo);

  final AppRepository _repo;

  List<District> _districts = [];
  List<Village> _villages = [];
  List<RouteWithBuses> _results = [];
  List<Favorite> _favorites = [];

  District? _selectedDistrict;
  bool _loadingDistricts = false;
  bool _loadingVillages = false;
  bool _loadingResults = false;
  bool _loadingFavorites = false;
  String? _error;

  List<District> get districts => _districts;
  List<Village> get villages => _villages;
  List<RouteWithBuses> get results => _results;
  List<Favorite> get favorites => _favorites;
  District? get selectedDistrict => _selectedDistrict;
  bool get loadingDistricts => _loadingDistricts;
  bool get loadingVillages => _loadingVillages;
  bool get loadingResults => _loadingResults;
  bool get loadingFavorites => _loadingFavorites;
  String? get error => _error;

  void clearError() {
    _error = null;
    notifyListeners();
  }

  void selectDistrict(District district) {
    _selectedDistrict = district;
    _villages = [];
    _results = [];
    notifyListeners();
    AppStorage.setDistrictId(district.id);
    loadVillages();
  }

  /// Restores a previously persisted district selection, if any.
  Future<bool> restoreDistrict() async {
    final id = await AppStorage.districtId;
    if (id == null) return false;
    final match = _districts.where((d) => d.id == id).firstOrNull;
    if (match == null) return false;
    selectDistrict(match);
    return true;
  }

  /// Detects the district from GPS and selects it. Returns false when
  /// detection is unavailable or nothing matches.
  Future<bool> autoDetectDistrict() async {
    final name = await DistrictDetector.detectDistrict();
    if (name == null) return false;
    final match = DistrictDetector.bestMatch(name, _districts);
    if (match == null) return false;
    selectDistrict(match);
    return true;
  }

  Future<void> loadDistricts() async {
    _loadingDistricts = true;
    _error = null;
    notifyListeners();
    try {
      _districts = await _repo.districts();
    } catch (e) {
      _error = e.toString();
    } finally {
      _loadingDistricts = false;
      notifyListeners();
    }
  }

  Future<void> loadVillages({String? query}) async {
    final district = _selectedDistrict;
    if (district == null) return;
    _loadingVillages = true;
    notifyListeners();
    try {
      _villages = await _repo.villages(district.id, query: query);
    } catch (e) {
      _error = e.toString();
    } finally {
      _loadingVillages = false;
      notifyListeners();
    }
  }

  Future<void> findRoutes({
    required int fromVillageId,
    required int toVillageId,
  }) async {
    final district = _selectedDistrict;
    if (district == null) return;
    _loadingResults = true;
    _error = null;
    notifyListeners();
    try {
      _results = await _repo.findRoutes(
        districtId: district.id,
        fromVillageId: fromVillageId,
        toVillageId: toVillageId,
      );
    } catch (e) {
      _error = e.toString();
    } finally {
      _loadingResults = false;
      notifyListeners();
    }
  }

  Future<void> loadFavorites() async {
    _loadingFavorites = true;
    notifyListeners();
    try {
      final deviceId = await AppStorage.deviceId();
      _favorites = await _repo.favorites(deviceId);
    } catch (e) {
      _error = e.toString();
    } finally {
      _loadingFavorites = false;
      notifyListeners();
    }
  }

  Future<void> removeFavorite(Favorite favorite) async {
    final deviceId = await AppStorage.deviceId();
    await _repo.deleteFavorite(favorite.id, deviceId);
    await loadFavorites();
  }
}
