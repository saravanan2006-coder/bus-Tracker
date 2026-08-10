import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

/// Client wrapper around Firebase Cloud Messaging.
///
/// Safe to run with no Firebase project configured (e.g. the local demo):
/// when the FIREBASE_* --dart-define values are absent, every call is a
/// no-op and returns null, so the app and its tests keep working unchanged.
///
/// To enable real push, supply Firebase web-app options at build time:
///   flutter run --dart-define=FIREBASE_API_KEY=... \
///     --dart-define=FIREBASE_APP_ID=... \
///     --dart-define=FIREBASE_MESSAGING_SENDER_ID=... \
///     --dart-define=FIREBASE_PROJECT_ID=... \
///     [--dart-define=FIREBASE_AUTH_DOMAIN=...]
class PushService {
  PushService._();

  static const String _apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const String _appId = String.fromEnvironment('FIREBASE_APP_ID');
  static const String _messagingSenderId =
      String.fromEnvironment('FIREBASE_MESSAGING_SENDER_ID');
  static const String _projectId =
      String.fromEnvironment('FIREBASE_PROJECT_ID');
  static const String _authDomain =
      String.fromEnvironment('FIREBASE_AUTH_DOMAIN');

  static Future<bool>? _init;
  static String? _token;

  /// True when Firebase configuration was supplied at build time.
  static bool get isConfigured =>
      _apiKey.isNotEmpty &&
      _appId.isNotEmpty &&
      _messagingSenderId.isNotEmpty &&
      _projectId.isNotEmpty;

  /// Requests notification permission and returns the device push token, or
  /// null when Firebase is not configured, permission is denied, or the
  /// platform cannot provide one (e.g. plain-HTTP web).
  static Future<String?> obtainToken() async {
    final ok = await _ensureInitialized();
    if (!ok) return null;
    try {
      final messaging = FirebaseMessaging.instance;
      final settings = await messaging.requestPermission();
      final status = settings.authorizationStatus;
      if (status != AuthorizationStatus.authorized &&
          status != AuthorizationStatus.provisional) {
        return null;
      }
      _token = await messaging.getToken();
      return _token;
    } catch (_) {
      return null;
    }
  }

  /// The device token from the last successful [obtainToken] call, if any.
  static String? get deviceToken => _token;

  /// Starts listening for token refresh, foreground messages and pushes that
  /// launched or resumed the app. Safe no-op when Firebase is not configured.
  static void startListening({
    void Function(String? title, String? body)? onMessage,
    void Function(String? title, String? body)? onMessageOpened,
  }) {
    _ensureInitialized().then((ok) {
      if (!ok) return;
      final messaging = FirebaseMessaging.instance;
      messaging.onTokenRefresh.listen((token) => _token = token);
      if (onMessage != null) {
        FirebaseMessaging.onMessage.listen((message) => onMessage(
            message.notification?.title, message.notification?.body));
      }
      if (onMessageOpened != null) {
        messaging.getInitialMessage().then((message) {
          if (message != null) {
            onMessageOpened(
                message.notification?.title, message.notification?.body);
          }
        });
        FirebaseMessaging.onMessageOpenedApp.listen((message) =>
            onMessageOpened(
                message.notification?.title, message.notification?.body));
      }
    });
  }

  static Future<bool> _ensureInitialized() {
    if (!isConfigured) return Future.value(false);
    return _init ??= _doInit();
  }

  static Future<bool> _doInit() async {
    try {
      await Firebase.initializeApp(
        options: FirebaseOptions(
          apiKey: _apiKey,
          appId: _appId,
          messagingSenderId: _messagingSenderId,
          projectId: _projectId,
          authDomain: _authDomain.isEmpty ? null : _authDomain,
        ),
      );
      return true;
    } catch (_) {
      return false;
    }
  }
}
