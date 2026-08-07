import 'package:flutter/foundation.dart';

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
  List<Village> _favoriteDetails = [];

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
  List<Village> get favoriteDetails => _favoriteDetails;
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
    loadVillages();
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
      final details = <Village>[];
      final district = _selectedDistrict;
      if (district != null) {
        for (final fav in _favorites) {
          try {
            final list = await _repo.villages(district.id, limit: 500);
            for (final v in list) {
              if (v.id == fav.fromVillageId || v.id == fav.toVillageId) {
                details.add(v);
              }
            }
          } catch (_) {
            // Favorites may reference villages from other districts.
          }
        }
      }
      _favoriteDetails = details;
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
