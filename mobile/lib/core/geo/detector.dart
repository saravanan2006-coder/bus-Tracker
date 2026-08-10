import 'dart:convert';

import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;

import '../models/models.dart';

/// Reverse-geocodes the user's GPS position to a Tamil Nadu district name
/// using OpenStreetMap's Nominatim. Used for "detect district automatically".
class DistrictDetector {
  DistrictDetector._();

  static const _nominatim =
      'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10';

  /// OSM spellings that differ from the backend's canonical census names.
  /// Keys and values are already normalized (lowercased, letters only).
  static const Map<String, String> _aliases = {
    'viluppuram': 'villupuram',
    'thoothukudi': 'thoothukkudi',
    'tuticorin': 'thoothukkudi',
    'kanyakumari': 'kanniyakumari',
    'nilgiris': 'thenilgiris',
    'thiruvarur': 'tiruvarur',
    'sivaganga': 'sivagangai',
    'thiruvallur': 'tiruvallur',
  };

  /// Lowercases a name, drops everything that is not a-z and applies known
  /// spelling aliases. "Viluppuram", "Villupuram" and "VILUPPURAM" all
  /// normalize to "villupuram".
  static String normalizeName(String name) {
    final key = name.toLowerCase().replaceAll(RegExp(r'[^a-z]'), '');
    return _aliases[key] ?? key;
  }

  /// Matches a raw district name against the backend's canonical list.
  /// Exact normalized match wins; otherwise the closest character-bigram
  /// match above a similarity threshold is returned (covers spellings that
  /// are not in the alias table).
  static District? bestMatch(String name, List<District> districts) {
    final normalized = normalizeName(name);
    for (final d in districts) {
      if (normalizeName(d.name) == normalized) return d;
    }
    District? best;
    var bestScore = 0.0;
    for (final d in districts) {
      final score = _similarity(normalized, normalizeName(d.name));
      if (score > bestScore) {
        bestScore = score;
        best = d;
      }
    }
    return bestScore >= 0.6 ? best : null;
  }

  /// Dice coefficient over character bigrams, 0..1.
  static double _similarity(String a, String b) {
    if (a == b) return 1;
    if (a.isEmpty || b.isEmpty) return 0;
    final Set<String> bigramsA = {};
    final Set<String> bigramsB = {};
    for (var i = 0; i < a.length - 1; i++) {
      bigramsA.add(a.substring(i, i + 2));
    }
    for (var i = 0; i < b.length - 1; i++) {
      bigramsB.add(b.substring(i, i + 2));
    }
    final intersection = bigramsA.intersection(bigramsB).length;
    return 2 * intersection / (bigramsA.length + bigramsB.length);
  }

  /// Returns the current position, or null if permission was denied.
  static Future<Position?> currentPosition() async {
    final granted = await ensureLocationPermission();
    if (!granted) return null;
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
    );
  }

  /// Checks location permission, requesting it first if it was denied.
  /// Returns true when access is granted (while-in-use or always).
  static Future<bool> ensureLocationPermission() async {
    var granted = await Geolocator.checkPermission();
    if (granted == LocationPermission.denied) {
      granted = await Geolocator.requestPermission();
    }
    return granted == LocationPermission.whileInUse ||
        granted == LocationPermission.always;
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

  /// Convenience: current position -> district name (or null on any failure,
  /// including permission denied, no location service or platform errors).
  static Future<String?> detectDistrict() async {
    try {
      final position = await currentPosition();
      if (position == null) return null;
      return await districtNameFor(position);
    } catch (_) {
      return null;
    }
  }
}
