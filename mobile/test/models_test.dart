import 'package:bus_tracker/core/models/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('District.fromJson', () {
    test('parses the public district payload', () {
      final d = District.fromJson(const {
        'id': 29,
        'name': 'Villupuram',
        'name_ta': 'விழுப்புரம்',
        'taluk_count': 9,
        'village_count': 1102,
      });
      expect(d.id, 29);
      expect(d.name, 'Villupuram');
      expect(d.nameTa, 'விழுப்புரம்');
      expect(d.talukCount, 9);
      expect(d.villageCount, 1102);
    });
  });

  group('Village.fromJson', () {
    test('parses a village row', () {
      final v = Village.fromJson(const {
        'id': 4,
        'taluk_id': 2,
        'district_id': 29,
        'name': 'Tindivanam',
        'name_ta': 'திண்டிவனம்',
        'place_type': 'town',
        'has_coords': true,
      });
      expect(v.id, 4);
      expect(v.districtId, 29);
      expect(v.hasCoords, isTrue);
    });
  });

  group('LivePosition.fromJson', () {
    test('parses a live websocket payload', () {
      final p = LivePosition.fromJson(const {
        'bus_id': 7,
        'trip_id': 3,
        'lat': 11.94,
        'lng': 79.49,
        'speed_kmh': 42.0,
        'ts': '2026-08-07T06:00:00+00:00',
        'anomalous': false,
        'stale': false,
      });
      expect(p.busId, 7);
      expect(p.tripId, 3);
      expect(p.speedKmh, 42.0);
      expect(p.stale, isFalse);
    });

    test('handles the end-of-trip broadcast', () {
      final p = LivePosition.fromJson(const {
        'bus_id': 7,
        'trip_id': 3,
        'ended': true,
        'ts': '2026-08-07T06:00:00+00:00',
      });
      expect(p.ended, isTrue);
    });
  });

  group('BusDetail.fromJson', () {
    test('parses the full detail payload with route and ETA', () {
      final b = BusDetail.fromJson(const {
        'id': 7,
        'bus_number': '21A',
        'bus_type': 'govt',
        'verified': false,
        'route': {
          'id': 1,
          'from_village': {'id': 1, 'name': 'Villupuram'},
          'to_village': {'id': 4, 'name': 'Tindivanam'},
          'distance_m': 42250,
          'stops': [
            {
              'village_id': 1,
              'seq': 0,
              'progress': 0.0,
              'village': {'id': 1, 'name': 'Villupuram'},
            },
            {
              'village_id': 4,
              'seq': 1,
              'progress': 1.0,
              'village': {'id': 4, 'name': 'Tindivanam'},
            },
          ],
        },
        'live': {
          'bus_id': 7,
          'trip_id': 3,
          'lat': 12.0,
          'lng': 79.55,
          'speed_kmh': 40.0,
          'ts': '2026-08-07T06:00:00+00:00',
        },
        'eta': {
          'progress': 0.42,
          'distance_remaining_m': 24505,
          'eta_minutes': 24.5,
          'predicted_speed_kmh': 60.0,
          'next_stop': {
            'village_id': 4,
            'seq': 1,
            'progress': 1.0,
            'eta_minutes': 5.0,
            'village': {'id': 4, 'name': 'Tindivanam'},
          },
        },
      });
      expect(b.busNumber, '21A');
      expect(b.route?.stops, hasLength(2));
      expect(b.route?.fromVillage?.name, 'Villupuram');
      expect(b.live?.lat, 12.0);
      expect(b.eta?.nextStop?.villageId, 4);
      expect(b.eta?.nextStop?.village?.name, 'Tindivanam');
    });
  });

  group('Trip.fromJson', () {
    test('parses a started trip', () {
      final t = Trip.fromJson(const {
        'id': 3,
        'bus_id': 7,
        'route_id': 1,
        'status': 'active',
        'started_at': '2026-08-07T05:30:00+00:00',
      });
      expect(t.id, 3);
      expect(t.busId, 7);
      expect(t.status, 'active');
    });
  });
}
