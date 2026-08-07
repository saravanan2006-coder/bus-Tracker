import 'package:flutter/foundation.dart';

import '../../../core/repository/app_repository.dart';
import '../../../core/storage/app_storage.dart';

/// Driver authentication flow (phone + OTP + JWT).
class AuthController extends ChangeNotifier {
  AuthController(this._repo);

  final AppRepository _repo;

  bool _busy = false;
  String? _error;

  bool get busy => _busy;
  String? get error => _error;

  Future<bool> requestOtp(String phone) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await _repo.requestOtp(phone);
      return true;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<bool> verifyOtp(String phone, String otp) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      final tokens = await _repo.verifyOtp(phone, otp);
      await AppStorage.saveTokens(
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        driverId: tokens.driverId,
      );
      _repo.setAccessToken(tokens.accessToken);
      return true;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  /// True when a previously stored session can be restored.
  Future<bool> restoreSession() async {
    final token = await AppStorage.accessToken;
    if (token == null) return false;
    _repo.setAccessToken(token);
    return true;
  }

  Future<void> logout() async {
    await AppStorage.clearTokens();
    _repo.setAccessToken(null);
  }
}
