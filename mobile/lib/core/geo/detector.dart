import 'dart:convert';

import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;

/// Reverse-geocodes the user's GPS position to a Tamil Nadu district name
/// using OpenStreetMap's Nominatim. Used for "detect district automatically".
class DistrictDetector {
  DistrictDetector._();

  static const _nominatim =
      'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10';

  /// Returns the current position, or null if permission was denied.
  static Future<Position?> currentPosition() async {
    var granted = await Geolocator.checkPermission();
    if (granted == LocationPermission.denied) {
      granted = await Geolocator.requestPermission();
    }
    if (granted == LocationPermission.denied ||
        granted == LocationPermission.deniedForever) {
      return null;
    }
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
    );
  }

  /// Resolves a position to a district name via Nominatim, or null.
  static Future<String?> districtNameFor(Position position) async {
    try {
      final url = Uri.parse(
        '$_nominatim&lat=${position.latitude}&lon=${position.longitude}',
      );
      final res = await http
          .get(
            url,
            headers: {'User-Agent': 'bus-tracker-mobile/1.0'},
          )
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) return null;
      final json = jsonDecode(res.body) as Map<String, dynamic>;
      final address = json['address'] as Map<String, dynamic>?;
      if (address == null) return null;
      for (final key in ['district', 'county', 'state_district']) {
        final value = address[key]?.toString();
        if (value != null && value.isNotEmpty) return value;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Convenience: current position -> district name (or null on any failure).
  static Future<String?> detectDistrict() async {
    final position = await currentPosition();
    if (position == null) return null;
    return districtNameFor(position);
  }
}
