import 'package:bus_tracker/core/config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppConfig URLs', () {
    test('rest API base targets localhost on the host', () {
      expect(AppConfig.apiBaseUrl, 'http://localhost:8000');
    });

    test('wsBaseUrl keeps the /api/v1 prefix the backend mounts under', () {
      expect(AppConfig.wsBaseUrl, 'ws://localhost:8000/api/v1/ws');
    });

    test('busWsUrl points at the live feed for one bus', () {
      expect(AppConfig.busWsUrl(7), 'ws://localhost:8000/api/v1/ws/bus/7');
    });
  });
}
