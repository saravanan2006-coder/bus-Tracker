import 'dart:math' as math;

/// Formatting helpers shared across screens.
class Format {
  Format._();

  static String distance(double meters) {
    if (meters >= 1000) {
      final km = meters / 1000;
      return '${km.toStringAsFixed(km >= 10 ? 0 : 1)} km';
    }
    return '${meters.round()} m';
  }

  static String etaMinutes(double minutes) {
    final rounded = minutes.round();
    if (rounded < 1) return '<1';
    if (rounded >= 60) {
      final h = rounded ~/ 60;
      final m = rounded % 60;
      return m == 0 ? '${h}h' : '${h}h ${m}m';
    }
    return '$rounded';
  }
}

/// Approximate haversine distance between two lat/lng points in metres.
double haversine(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371008.8;
  final dLat = _rad(lat2 - lat1);
  final dLng = _rad(lng2 - lng1);
  final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.cos(_rad(lat1)) *
          math.cos(_rad(lat2)) *
          math.sin(dLng / 2) *
          math.sin(dLng / 2);
  return 2 * r * math.asin(math.min(1.0, math.sqrt(a)));
}

double _rad(double degrees) => degrees * math.pi / 180.0;
