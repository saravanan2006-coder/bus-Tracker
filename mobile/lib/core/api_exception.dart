/// A typed exception for API errors, carrying the HTTP status and a
/// user-facing message when the backend provides one.
class ApiException implements Exception {
  const ApiException(this.status, this.message, {this.code});

  final int status;
  final String message;
  final String? code;

  bool get isUnauthorized => status == 401;
  bool get isConflict => status == 409;
  bool get isRateLimited => status == 429;

  @override
  String toString() => 'ApiException($status): $message';
}
