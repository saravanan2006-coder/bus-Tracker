import 'package:bus_tracker/core/geo.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Format.distance', () {
    test('rounds short distances to metres', () {
      expect(Format.distance(499.6), '500 m');
      expect(Format.distance(0), '0 m');
    });

    test('switches to km above a kilometre', () {
      expect(Format.distance(1000), '1.0 km');
      expect(Format.distance(1500), '1.5 km');
      expect(Format.distance(12300), '12 km');
    });
  });

  group('Format.etaMinutes', () {
    test('handles sub-minute ETAs', () {
      expect(Format.etaMinutes(0.4), '<1');
    });

    test('rounds to whole minutes', () {
      expect(Format.etaMinutes(59.4), '59');
      expect(Format.etaMinutes(3.1), '3');
    });

    test('formats hour and minute combinations', () {
      expect(Format.etaMinutes(59.6), '1h');
      expect(Format.etaMinutes(90.4), '1h 30m');
      expect(Format.etaMinutes(120), '2h');
    });
  });

  group('haversine', () {
    test('computes a known short distance', () {
      final d = haversine(11.0, 79.0, 11.01, 79.0);
      expect(d, closeTo(1112, 5));
    });

    test('is symmetric', () {
      final ab = haversine(11.94, 79.49, 12.24, 79.66);
      final ba = haversine(12.24, 79.66, 11.94, 79.49);
      expect(ab, closeTo(ba, 0.001));
    });
  });
}
