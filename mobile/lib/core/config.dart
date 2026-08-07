import 'dart:io' show Platform;

/// Runtime configuration. Override at build time with:
///   flutter run --dart-define=API_BASE_URL=https://api.example.com
///
/// Defaults target a locally running FastAPI backend (Android emulator
/// reaches the host machine via 10.0.2.2).
class AppConfig {
  AppConfig._();

  static const String _apiBaseOverride = String.fromEnvironment('API_BASE_URL');

  static String get apiBaseUrl {
    if (_apiBaseOverride.isNotEmpty) return _apiBaseOverride;
    if (Platform.isAndroid) return 'http://10.0.2.2:8000';
    return 'http://localhost:8000';
  }

  static const String apiPrefix = '/api/v1';

  /// WebSocket root. The backend mounts the WS router under [apiPrefix] too
  /// (same as the REST API), so the path must include it.
  static String get wsBaseUrl {
    final api = apiBaseUrl.replaceFirst(RegExp(r'^http'), 'ws');
    return '$api$apiPrefix/ws';
  }

  /// Live position feed for a single bus.
  static String busWsUrl(int busId) => '$wsBaseUrl/bus/$busId';

  // Tracking cadence (must match backend expectations).
  static const Duration movingInterval = Duration(seconds: 5);
  static const Duration stoppedInterval = Duration(seconds: 15);
  static const double stoppedSpeedKmh = 5.0;

  // Map tiles (free OSM; production should switch to a commercial tile host).
  static const String tileUrlTemplate =
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  static const String userAgentPackageName = 'in.bustracker.app';

  static const String appName = 'BusTracker';
}
