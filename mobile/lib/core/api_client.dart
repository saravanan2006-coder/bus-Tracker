import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'config.dart';

/// Thin HTTP wrapper around the FastAPI backend.
///
/// - Adds the bearer token for authenticated (driver) calls.
/// - Normalises all failures into [ApiException].
/// - Never throws on network errors; those surface as ApiException(0, ...)
///   so callers can show a friendly "check your connection" message.
class ApiClient {
  ApiClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  final http.Client _http;
  String? _accessToken;

  void setAccessToken(String? token) => _accessToken = token;

  String get _base => '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}';

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    if (query != null && query.isNotEmpty) {
      final params = <String, String>{
        for (final e in query.entries)
          if (e.value != null) e.key: e.value.toString(),
      };
      return Uri.parse('$_base$path').replace(queryParameters: params);
    }
    return Uri.parse('$_base$path');
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
      };

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    final res = await _send(() => _http.get(_uri(path, query), headers: _headers));
    return _decode(res);
  }

  Future<dynamic> post(String path, {Object? body, bool raw = false}) async {
    final res = await _send(
      () => _http.post(
        _uri(path),
        headers: _headers,
        body: jsonEncode(body ?? {}),
      ),
    );
    return _decode(res);
  }

  Future<dynamic> delete(String path, {Object? body, Map<String, dynamic>? query}) async {
    final res = await _send(
      () => _http.delete(
        _uri(path, query),
        headers: _headers,
        body: body == null ? null : jsonEncode(body),
      ),
    );
    return _decode(res);
  }

  Future<http.Response> _send(Future<http.Response> Function() request) async {
    try {
      final res = await request().timeout(const Duration(seconds: 15));
      if (res.statusCode >= 200 && res.statusCode < 300) return res;
      throw _toException(res);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException(0, 'Request timed out. Please try again.');
    } catch (_) {
      throw const ApiException(
          0, 'Cannot reach the server. Check your internet connection.');
    }
  }

  ApiException _toException(http.Response res) {
    String message = 'Something went wrong (${res.statusCode}).';
    String? code;
    try {
      final body = jsonDecode(res.body);
      final detail = body['detail'];
      if (detail is Map) {
        message = detail['message']?.toString() ?? message;
        code = detail['code']?.toString();
      } else if (detail is String) {
        message = detail;
      } else if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] != null) {
          message = first['msg'].toString();
        }
      }
    } catch (_) {
      // Non-JSON error body; keep the default message.
    }
    return ApiException(res.statusCode, message, code: code);
  }

  dynamic _decode(http.Response res) {
    if (res.body.isEmpty) return null;
    return jsonDecode(utf8.decode(res.bodyBytes));
  }
}
