import 'dart:convert';

import '../api_client.dart';
import '../models/models.dart';

/// Typed access to the BusTracker API.
///
/// Both the public (guest) and driver (authed) flows go through this class.
/// The driver's access token is read from secure storage and attached to
/// every request by the [ApiClient].
class AppRepository {
  AppRepository(this._api);

  final ApiClient _api;

  /// Attaches (or clears) the driver's access token for future requests.
  void setAccessToken(String? token) => _api.setAccessToken(token);

  // ------------------------------------------------------------------ //
  // Auth (driver)
  // ------------------------------------------------------------------ //
  Future<void> requestOtp(String phone) async {
    await _api.post('/auth/driver/otp', body: {'phone': phone});
  }

  Future<TokenResponse> verifyOtp(String phone, String otp) async {
    final json = await _api.post(
      '/auth/driver/verify',
      body: {'phone': phone, 'otp': otp},
    ) as Map<String, dynamic>;
    return TokenResponse.fromJson(json);
  }

  Future<DriverProfile> me() async {
    final json = await _api.get('/auth/me') as Map<String, dynamic>;
    final data = json['data'] as Map<String, dynamic>;
    return DriverProfile.fromJson(data);
  }

  // ------------------------------------------------------------------ //
  // Public: districts & villages
  // ------------------------------------------------------------------ //
  Future<List<District>> districts() async {
    final json = await _api.get('/districts') as List<dynamic>;
    return json
        .map((d) => District.fromJson(d as Map<String, dynamic>))
        .toList();
  }

  Future<List<Village>> villages(
    int districtId, {
    String? query,
    int limit = 100,
  }) async {
    final json = await _api.get(
      '/districts/$districtId/villages',
      query: {
        if (query != null && query.isNotEmpty) 'q': query,
        'limit': limit,
      },
    ) as List<dynamic>;
    return json
        .map((v) => Village.fromJson(v as Map<String, dynamic>))
        .toList();
  }

  // ------------------------------------------------------------------ //
  // Public: routes & buses
  // ------------------------------------------------------------------ //
  Future<List<RouteWithBuses>> findRoutes({
    required int districtId,
    required int fromVillageId,
    required int toVillageId,
  }) async {
    final json = await _api.get(
      '/routes/find',
      query: {
        'district_id': districtId,
        'from_village_id': fromVillageId,
        'to_village_id': toVillageId,
      },
    ) as Map<String, dynamic>;
    final data = json['data'] as List<dynamic>? ?? [];
    return data
        .map((r) => RouteWithBuses.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  Future<RouteInfo> route(int routeId) async {
    final json = await _api.get('/routes/$routeId') as Map<String, dynamic>;
    return RouteInfo.fromJson(json);
  }

  Future<BusDetail> busDetail(int busId) async {
    final json = await _api.get('/buses/$busId') as Map<String, dynamic>;
    return BusDetail.fromJson(json['data'] as Map<String, dynamic>);
  }

  Future<List<Map<String, dynamic>>> busHistory(int busId) async {
    final json = await _api.get('/buses/$busId/history') as Map<String, dynamic>;
    final data = json['data'] as Map<String, dynamic>;
    return (data['trail'] as List<dynamic>).cast<Map<String, dynamic>>();
  }

  // ------------------------------------------------------------------ //
  // Public: favorites & alerts
  // ------------------------------------------------------------------ //
  Future<void> addFavorite({
    required String deviceId,
    required int fromVillageId,
    required int toVillageId,
  }) async {
    await _api.post('/favorites', body: {
      'device_id': deviceId,
      'from_village_id': fromVillageId,
      'to_village_id': toVillageId,
    });
  }

  Future<List<Favorite>> favorites(String deviceId) async {
    final json = await _api.get('/favorites', query: {'device_id': deviceId})
        as Map<String, dynamic>;
    final data = json['data'] as List<dynamic>? ?? [];
    return data
        .map((f) => Favorite.fromJson(f as Map<String, dynamic>))
        .toList();
  }

  Future<void> deleteFavorite(int favoriteId, String deviceId) async {
    await _api.delete(
      '/favorites/$favoriteId',
      query: {'device_id': deviceId},
    );
  }

  Future<void> subscribeAlert({
    required String deviceId,
    required int busId,
    required int stopVillageId,
    String? fcmToken,
    double distanceM = 1000,
  }) async {
    await _api.post('/alerts', body: {
      'device_id': deviceId,
      'bus_id': busId,
      'stop_village_id': stopVillageId,
      'fcm_token': fcmToken,
      'distance_m': distanceM,
    });
  }

  // ------------------------------------------------------------------ //
  // Driver: buses & routes
  // ------------------------------------------------------------------ //
  Future<List<Bus>> myBuses() async {
    final json = await _api.get('/driver/buses') as List<dynamic>;
    return json.map((b) => Bus.fromJson(b as Map<String, dynamic>)).toList();
  }

  Future<Bus> registerBus({
    required String busNumber,
    required String rtoNumber,
    required String busType,
    String? busName,
  }) async {
    final json = await _api.post('/driver/buses', body: {
      'bus_number': busNumber,
      'bus_name': busName,
      'bus_type': busType,
      'rto_number': rtoNumber,
    }) as Map<String, dynamic>;
    return Bus.fromJson(json);
  }

  Future<RouteInfo> buildRoute({
    required int districtId,
    required int fromVillageId,
    required int toVillageId,
  }) async {
    final json = await _api.post('/driver/routes/build', body: {
      'district_id': districtId,
      'from_village_id': fromVillageId,
      'to_village_id': toVillageId,
    }) as Map<String, dynamic>;
    return RouteInfo.fromJson(json);
  }

  Future<void> assignRoute({required int busId, required int routeId}) async {
    await _api.post(
      '/driver/buses/$busId/assign-route',
      body: {'route_id': routeId},
    );
  }

  Future<List<DriverRoute>> driverRoutes(int districtId) async {
    final json = await _api.get(
      '/driver/routes',
      query: {'district_id': districtId},
    ) as List<dynamic>;
    return json
        .map((r) => DriverRoute.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  // ------------------------------------------------------------------ //
  // Driver: trips
  // ------------------------------------------------------------------ //
  Future<Trip> startTrip({required int busId, required int routeId}) async {
    final json = await _api.post(
      '/driver/trips',
      body: {'bus_id': busId, 'route_id': routeId},
    ) as Map<String, dynamic>;
    return Trip.fromJson(json);
  }

  Future<Trip?> activeTrip() async {
    final json = await _api.get('/driver/trips/active') as Map<String, dynamic>;
    final data = json['data'];
    if (data == null) return null;
    return Trip.fromJson(data as Map<String, dynamic>);
  }

  Future<void> endTrip(int tripId) async {
    await _api.post('/driver/trips/$tripId/end');
  }

  /// Sends one GPS fix. Returns true when the backend accepted it.
  Future<bool> sendLocation({
    required int tripId,
    required double lat,
    required double lng,
    double? speedKmh,
    double? heading,
    required DateTime ts,
  }) async {
    final json = await _api.post(
      '/driver/trips/$tripId/location',
      body: {
        'lat': lat,
        'lng': lng,
        'speed_kmh': speedKmh,
        'heading': heading,
        'ts': ts.toUtc().toIso8601String(),
      },
    ) as Map<String, dynamic>;
    return (json['data'] as Map<String, dynamic>)['accepted'] as bool? ?? false;
  }
}

class TokenResponse {
  const TokenResponse({
    required this.accessToken,
    required this.refreshToken,
    required this.driverId,
  });

  final String accessToken;
  final String refreshToken;
  final int driverId;

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
        driverId: (json['driver_id'] as num).toInt(),
      );
}

/// A single buffered GPS fix as stored offline. Serialisable to/from JSON.
class BufferedFix {
  const BufferedFix({
    required this.tripId,
    required this.lat,
    required this.lng,
    this.speedKmh,
    this.heading,
    required this.ts,
  });

  final int tripId;
  final double lat;
  final double lng;
  final double? speedKmh;
  final double? heading;
  final DateTime ts;

  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'lat': lat,
        'lng': lng,
        'speed_kmh': speedKmh,
        'heading': heading,
        'ts': ts.toUtc().toIso8601String(),
      };

  static BufferedFix fromJson(Map<String, dynamic> json) => BufferedFix(
        tripId: (json['trip_id'] as num).toInt(),
        lat: (json['lat'] as num).toDouble(),
        lng: (json['lng'] as num).toDouble(),
        speedKmh: (json['speed_kmh'] as num?)?.toDouble(),
        heading: (json['heading'] as num?)?.toDouble(),
        ts: DateTime.parse(json['ts'] as String),
      );

  String encode() => jsonEncode(toJson());
}
