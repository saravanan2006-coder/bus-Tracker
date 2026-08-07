import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// Persists small, sensitive values (tokens) in the platform keystore and
/// lightweight app preferences (language, device id) in SharedPreferences.
class AppStorage {
  AppStorage._();

  static const _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _kAccessToken = 'access_token';
  static const _kRefreshToken = 'refresh_token';
  static const _kDriverId = 'driver_id';
  static const _kLanguage = 'language';
  static const _kDeviceId = 'device_id';

  // ------------------------------------------------------------------ //
  // Secure (tokens)
  // ------------------------------------------------------------------ //
  static Future<String?> get accessToken async =>
      _secure.read(key: _kAccessToken);

  static Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
    required int driverId,
  }) async {
    await _secure.write(key: _kAccessToken, value: accessToken);
    await _secure.write(key: _kRefreshToken, value: refreshToken);
    await _secure.write(key: _kDriverId, value: '$driverId');
  }

  static Future<void> clearTokens() async {
    await _secure.delete(key: _kAccessToken);
    await _secure.delete(key: _kRefreshToken);
    await _secure.delete(key: _kDriverId);
  }

  // ------------------------------------------------------------------ //
  // Preferences
  // ------------------------------------------------------------------ //
  static Future<String> get language async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kLanguage) ?? 'ta';
  }

  static Future<void> setLanguage(String value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kLanguage, value);
  }

  /// Stable anonymous id for favorites/alerts. Generated once per install.
  static Future<String> deviceId() async {
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString(_kDeviceId);
    if (id == null || id.isEmpty) {
      id = const Uuid().v4();
      await prefs.setString(_kDeviceId, id);
    }
    return id;
  }
}

/// JSON-encoded offline buffer for unsent GPS fixes (survives app restarts).
class OfflineBuffer {
  OfflineBuffer._();

  static const _kKey = 'offline_locations';

  static Future<List<Map<String, dynamic>>> read() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kKey);
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list.cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  static Future<void> add(Map<String, dynamic> fix) async {
    final items = await read();
    items.add(fix);
    // Cap the buffer so it cannot grow without bound.
    if (items.length > 500) {
      items.removeRange(0, items.length - 500);
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kKey, jsonEncode(items));
  }

  static Future<void> replace(List<Map<String, dynamic>> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kKey, jsonEncode(items));
  }
}
