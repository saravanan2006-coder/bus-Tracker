import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';
import '../models/models.dart';

/// Subscribes to a bus's live position feed over WebSocket.
///
/// The backend sends the last known position immediately on connect, then
/// pushes every new fix. On error/close the stream terminates and the caller
/// decides whether to reconnect (with backoff).
class BusWsClient {
  BusWsClient(this.busId);

  final int busId;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  StreamController<LivePosition>? _controller;

  Stream<LivePosition> get positions => _controller!.stream;

  Future<void> connect() async {
    await disconnect();
    _controller = StreamController<LivePosition>.broadcast();
    _channel = WebSocketChannel.connect(Uri.parse(AppConfig.busWsUrl(busId)));
    _sub = _channel!.stream.listen(
      (raw) {
        try {
          final json = jsonDecode(raw as String) as Map<String, dynamic>;
          _controller!.add(LivePosition.fromJson(json));
        } catch (_) {
          // Ignore malformed frames; the backend is authoritative.
        }
      },
      onError: (Object _) => _controller!.close(),
      onDone: () => _controller!.close(),
    );
  }

  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
    await _channel?.sink.close();
    _channel = null;
    if (_controller != null && !_controller!.isClosed) {
      await _controller!.close();
    }
    _controller = null;
  }
}
