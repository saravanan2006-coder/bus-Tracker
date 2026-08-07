import 'package:flutter/foundation.dart';

@immutable
class District {
  const District({
    required this.id,
    required this.name,
    this.nameTa,
    required this.talukCount,
    required this.villageCount,
  });

  final int id;
  final String name;
  final String? nameTa;
  final int talukCount;
  final int villageCount;

  factory District.fromJson(Map<String, dynamic> json) => District(
        id: json['id'] as int,
        name: json['name'] as String,
        nameTa: json['name_ta'] as String?,
        talukCount: (json['taluk_count'] as num?)?.toInt() ?? 0,
        villageCount: (json['village_count'] as num?)?.toInt() ?? 0,
      );
}

@immutable
class Village {
  const Village({
    required this.id,
    required this.talukId,
    required this.districtId,
    required this.name,
    this.nameTa,
    required this.placeType,
    required this.hasCoords,
  });

  final int id;
  final int talukId;
  final int districtId;
  final String name;
  final String? nameTa;
  final String placeType;
  final bool hasCoords;

  factory Village.fromJson(Map<String, dynamic> json) => Village(
        id: json['id'] as int,
        talukId: json['taluk_id'] as int,
        districtId: json['district_id'] as int,
        name: json['name'] as String,
        nameTa: json['name_ta'] as String?,
        placeType: json['place_type'] as String? ?? '',
        hasCoords: json['has_coords'] as bool? ?? false,
      );
}

@immutable
class RouteInfo {
  const RouteInfo({
    required this.id,
    required this.districtId,
    required this.fromVillageId,
    required this.toVillageId,
    required this.polyline,
    this.distanceM,
    required this.status,
  });

  final int id;
  final int districtId;
  final int fromVillageId;
  final int toVillageId;
  final List<List<double>> polyline;
  final double? distanceM;
  final String status;

  factory RouteInfo.fromJson(Map<String, dynamic> json) => RouteInfo(
        id: json['id'] as int,
        districtId: json['district_id'] as int,
        fromVillageId: json['from_village_id'] as int,
        toVillageId: json['to_village_id'] as int,
        polyline: (json['polyline'] as List<dynamic>? ?? [])
            .map((p) => (p as List<dynamic>)
                .map((v) => (v as num).toDouble())
                .toList())
            .toList(),
        distanceM: (json['distance_m'] as num?)?.toDouble(),
        status: json['status'] as String? ?? '',
      );
}

@immutable
class StopSummary {
  const StopSummary({
    required this.villageId,
    required this.seq,
    required this.progress,
    this.village,
  });

  final int villageId;
  final int seq;
  final double progress;
  final VillageSummary? village;

  factory StopSummary.fromJson(Map<String, dynamic> json) => StopSummary(
        villageId: json['village_id'] as int,
        seq: (json['seq'] as num?)?.toInt() ?? 0,
        progress: (json['progress'] as num?)?.toDouble() ?? 0,
        village: json['village'] == null
            ? null
            : VillageSummary.fromJson(json['village'] as Map<String, dynamic>),
      );
}

@immutable
class VillageSummary {
  const VillageSummary({
    required this.id,
    required this.name,
    this.nameTa,
    this.talukId,
  });

  final int id;
  final String name;
  final String? nameTa;
  final int? talukId;

  factory VillageSummary.fromJson(Map<String, dynamic> json) => VillageSummary(
        id: json['id'] as int,
        name: json['name'] as String,
        nameTa: json['name_ta'] as String?,
        talukId: json['taluk_id'] as int?,
      );
}

@immutable
class RouteDetail {
  const RouteDetail({
    required this.id,
    this.fromVillage,
    this.toVillage,
    this.distanceM,
    required this.stops,
  });

  final int id;
  final VillageSummary? fromVillage;
  final VillageSummary? toVillage;
  final double? distanceM;
  final List<StopSummary> stops;

  factory RouteDetail.fromJson(Map<String, dynamic> json) => RouteDetail(
        id: json['id'] as int,
        fromVillage: json['from_village'] == null
            ? null
            : VillageSummary.fromJson(json['from_village'] as Map<String, dynamic>),
        toVillage: json['to_village'] == null
            ? null
            : VillageSummary.fromJson(json['to_village'] as Map<String, dynamic>),
        distanceM: (json['distance_m'] as num?)?.toDouble(),
        stops: (json['stops'] as List<dynamic>? ?? [])
            .map((s) => StopSummary.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}

@immutable
class LivePosition {
  const LivePosition({
    required this.busId,
    this.tripId,
    this.lat,
    this.lng,
    this.speedKmh,
    this.heading,
    required this.ts,
    this.anomalous = false,
    this.stale = false,
    this.ended = false,
  });

  final int busId;
  final int? tripId;
  final double? lat;
  final double? lng;
  final double? speedKmh;
  final double? heading;
  final DateTime ts;
  final bool anomalous;
  final bool stale;
  final bool ended;

  bool get hasPosition => lat != null && lng != null;

  factory LivePosition.fromJson(Map<String, dynamic> json) => LivePosition(
        busId: (json['bus_id'] as num?)?.toInt() ?? 0,
        tripId: (json['trip_id'] as num?)?.toInt(),
        lat: (json['lat'] as num?)?.toDouble(),
        lng: (json['lng'] as num?)?.toDouble(),
        speedKmh: (json['speed_kmh'] as num?)?.toDouble(),
        heading: (json['heading'] as num?)?.toDouble(),
        ts: DateTime.tryParse(json['ts'] as String? ?? '')?.toLocal() ?? DateTime.now(),
        anomalous: json['anomalous'] as bool? ?? false,
        stale: json['stale'] as bool? ?? false,
        ended: json['ended'] as bool? ?? false,
      );
}

@immutable
class EtaInfo {
  const EtaInfo({
    required this.progress,
    required this.distanceRemainingM,
    required this.etaMinutes,
    this.predictedSpeedKmh,
    this.nextStop,
  });

  final double progress;
  final double distanceRemainingM;
  final double etaMinutes;
  final double? predictedSpeedKmh;
  final StopSummary? nextStop;

  factory EtaInfo.fromJson(Map<String, dynamic> json) => EtaInfo(
        progress: (json['progress'] as num?)?.toDouble() ?? 0,
        distanceRemainingM: (json['distance_remaining_m'] as num?)?.toDouble() ?? 0,
        etaMinutes: (json['eta_minutes'] as num?)?.toDouble() ?? 0,
        predictedSpeedKmh: (json['predicted_speed_kmh'] as num?)?.toDouble(),
        nextStop: json['next_stop'] == null
            ? null
            : StopSummary.fromJson(json['next_stop'] as Map<String, dynamic>),
      );
}

@immutable
class BusDetail {
  const BusDetail({
    required this.id,
    required this.busNumber,
    this.busName,
    required this.busType,
    this.rtoNumber,
    required this.verified,
    this.route,
    this.live,
    this.eta,
  });

  final int id;
  final String busNumber;
  final String? busName;
  final String busType;
  final String? rtoNumber;
  final bool verified;
  final RouteDetail? route;
  final LivePosition? live;
  final EtaInfo? eta;

  factory BusDetail.fromJson(Map<String, dynamic> json) => BusDetail(
        id: json['id'] as int,
        busNumber: json['bus_number'] as String,
        busName: json['bus_name'] as String?,
        busType: json['bus_type'] as String? ?? '',
        rtoNumber: json['rto_number'] as String?,
        verified: json['verified'] as bool? ?? false,
        route: json['route'] == null
            ? null
            : RouteDetail.fromJson(json['route'] as Map<String, dynamic>),
        live: json['live'] == null
            ? null
            : LivePosition.fromJson(json['live'] as Map<String, dynamic>),
        eta: json['eta'] == null
            ? null
            : EtaInfo.fromJson(json['eta'] as Map<String, dynamic>),
      );
}

@immutable
class RouteWithBuses {
  const RouteWithBuses({required this.route, required this.buses});

  final RouteInfo route;
  final List<BusDetail> buses;

  factory RouteWithBuses.fromJson(Map<String, dynamic> json) => RouteWithBuses(
        route: RouteInfo.fromJson(json['route'] as Map<String, dynamic>),
        buses: (json['buses'] as List<dynamic>? ?? [])
            .map((b) => BusDetail.fromJson(b as Map<String, dynamic>))
            .toList(),
      );
}

@immutable
class Bus {
  const Bus({
    required this.id,
    required this.busNumber,
    this.busName,
    required this.busType,
    required this.rtoNumber,
    required this.verificationStatus,
    this.routeId,
  });

  final int id;
  final String busNumber;
  final String? busName;
  final String busType;
  final String rtoNumber;
  final String verificationStatus;
  final int? routeId;

  factory Bus.fromJson(Map<String, dynamic> json) => Bus(
        id: json['id'] as int,
        busNumber: json['bus_number'] as String,
        busName: json['bus_name'] as String?,
        busType: json['bus_type'] as String? ?? '',
        rtoNumber: json['rto_number'] as String? ?? '',
        verificationStatus: json['verification_status'] as String? ?? 'pending',
        routeId: json['route_id'] as int?,
      );
}

@immutable
class DriverRoute {
  const DriverRoute({
    required this.id,
    required this.fromVillageId,
    required this.toVillageId,
    this.distanceM,
    required this.status,
  });

  final int id;
  final int fromVillageId;
  final int toVillageId;
  final double? distanceM;
  final String status;

  factory DriverRoute.fromJson(Map<String, dynamic> json) => DriverRoute(
        id: json['id'] as int,
        fromVillageId: json['from_village_id'] as int,
        toVillageId: json['to_village_id'] as int,
        distanceM: (json['distance_m'] as num?)?.toDouble(),
        status: json['status'] as String? ?? '',
      );
}

@immutable
class Trip {
  const Trip({
    required this.id,
    required this.busId,
    this.routeId,
    required this.status,
    required this.startedAt,
  });

  final int id;
  final int busId;
  final int? routeId;
  final String status;
  final DateTime startedAt;

  factory Trip.fromJson(Map<String, dynamic> json) => Trip(
        id: json['id'] as int,
        busId: json['bus_id'] as int,
        routeId: json['route_id'] as int?,
        status: json['status'] as String? ?? '',
        startedAt:
            DateTime.tryParse(json['started_at'] as String? ?? '')?.toLocal() ??
                DateTime.now(),
      );
}

@immutable
class DriverProfile {
  const DriverProfile({
    required this.id,
    required this.phone,
    this.name,
    required this.language,
  });

  final int id;
  final String phone;
  final String? name;
  final String language;

  factory DriverProfile.fromJson(Map<String, dynamic> json) => DriverProfile(
        id: json['id'] as int,
        phone: json['phone'] as String,
        name: json['name'] as String?,
        language: json['language'] as String? ?? 'ta',
      );
}

@immutable
class Favorite {
  const Favorite({
    required this.id,
    required this.fromVillageId,
    required this.toVillageId,
  });

  final int id;
  final int fromVillageId;
  final int toVillageId;

  factory Favorite.fromJson(Map<String, dynamic> json) => Favorite(
        id: json['id'] as int,
        fromVillageId: json['from_village_id'] as int,
        toVillageId: json['to_village_id'] as int,
      );
}
