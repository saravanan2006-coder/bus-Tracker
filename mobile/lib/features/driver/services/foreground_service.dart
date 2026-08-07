import 'package:flutter_foreground_task/flutter_foreground_task.dart';

/// Android foreground-service keepalive for the duration of a trip.
///
/// A foreground service keeps the app process (and therefore the
/// [LocationTracker] Dart timers) running while the app is backgrounded.
/// This wrapper is safe on platforms without the plugin configured: every
/// call is guarded so a failure only means the app keeps tracking in the
/// foreground instead.
class ForegroundService {
  ForegroundService._();

  static bool _inited = false;

  static Future<void> _ensureInit() async {
    if (_inited) return;
    _inited = true;
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'bus_tracker_trip',
        channelName: 'Trip location sharing',
        channelDescription:
            'Shows a notification while the driver is sharing the bus location.',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(60000),
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  static Future<void> start({
    required String title,
    required String text,
  }) async {
    try {
      await _ensureInit();
      if (await FlutterForegroundTask.isRunningService) return;
      await FlutterForegroundTask.startService(
        serviceId: 256,
        notificationTitle: title,
        notificationText: text,
        callback: keepAliveCallback,
      );
    } catch (_) {
      // Background keepalive unavailable; tracking continues in foreground.
    }
  }

  static Future<void> stop() async {
    try {
      await FlutterForegroundTask.stopService();
    } catch (_) {
      // Ignore; nothing to stop.
    }
  }
}

@pragma('vm:entry-point')
void keepAliveCallback() {
  FlutterForegroundTask.setTaskHandler(KeepAliveHandler());
}

/// Keeps the process alive while a trip is sharing. All real work happens on
/// the main isolate (see LocationTracker); this handler only exists so the
/// Android OS does not suspend the app in the background.
class KeepAliveHandler extends TaskHandler {
  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {}

  @override
  void onRepeatEvent(DateTime timestamp) {}

  @override
  Future<void> onDestroy(DateTime timestamp) async {}
}
