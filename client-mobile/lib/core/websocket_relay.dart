/// Cloud Relay WebSocket Client.
/// Connects to TinyPOS Server at wss://.../ws/client?api_key=...&client_name=...
/// and pipes incoming print jobs to the local Bluetooth thermal printer.
library;

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'background_relay_service.dart';
import 'ble_printer_manager.dart';
import 'storage_service.dart';

enum CloudRelayStatus {
  disconnected,
  connecting,
  connected,
  unauthorized,
  error,
}

class WebSocketRelayService extends ChangeNotifier {
  static final WebSocketRelayService _instance =
      WebSocketRelayService._internal();
  factory WebSocketRelayService() => _instance;
  WebSocketRelayService._internal();

  StorageService? _storage;
  BlePrinterManager? _bleManager;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;

  bool _isManualStop = false;
  CloudRelayStatus _status = CloudRelayStatus.disconnected;
  CloudRelayStatus get status => _status;

  String? _assignedGroup;
  String? get assignedGroup => _assignedGroup;

  String? _statusMessage;
  String? get statusMessage => _statusMessage;

  int _jobsReceivedCount = 0;
  int get jobsReceivedCount => _jobsReceivedCount;

  void init(StorageService storage, BlePrinterManager bleManager) {
    _storage = storage;
    _bleManager = bleManager;

    // Listen to printer status changes to report to cloud
    _bleManager?.addListener(_onPrinterStatusChanged);
  }

  void _setStatus(CloudRelayStatus status, [String? message]) {
    _status = status;
    _statusMessage = message;
    notifyListeners();
  }

  /// Connect to the TinyPOS cloud relay WebSocket.
  Future<void> connect() async {
    _isManualStop = false;
    _reconnectTimer?.cancel();

    final serverUrl = _storage?.serverUrl ?? '';
    final apiKey = _storage?.clientApiKey ?? '';
    final clientName = _storage?.terminalName ?? 'Mobile Terminal';

    if (serverUrl.isEmpty || apiKey.isEmpty) {
      _setStatus(
        CloudRelayStatus.unauthorized,
        'Server URL and Client API Key are required',
      );
      return;
    }

    // Convert http/https to ws/wss if needed
    String wsUrl = serverUrl.trim();
    if (wsUrl.startsWith('https://')) {
      wsUrl = wsUrl.replaceFirst('https://', 'wss://');
    } else if (wsUrl.startsWith('http://')) {
      wsUrl = wsUrl.replaceFirst('http://', 'ws://');
    } else if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
      wsUrl = 'wss://$wsUrl';
    }

    // Strip trailing slashes
    while (wsUrl.endsWith('/')) {
      wsUrl = wsUrl.substring(0, wsUrl.length - 1);
    }

    // Append endpoint if not present
    if (!wsUrl.contains('/ws/client')) {
      wsUrl = '$wsUrl/ws/client';
    }

    final uri = Uri.parse(
      '$wsUrl?api_key=${Uri.encodeComponent(apiKey)}&client_name=${Uri.encodeComponent(clientName)}',
    );

    _setStatus(CloudRelayStatus.connecting, 'Connecting to Cloud Relay...');

    try {
      await _disconnectInternal();
      _channel = WebSocketChannel.connect(uri);

      _sub = _channel!.stream.listen(
        _onMessage,
        onError: (err) {
          _setStatus(CloudRelayStatus.error, 'Relay error: $err');
          _scheduleReconnect();
        },
        onDone: () {
          if (!_isManualStop) {
            _setStatus(CloudRelayStatus.disconnected, 'Connection closed');
            _scheduleReconnect();
          }
        },
      );

      _startHeartbeat();
    } catch (e) {
      _setStatus(CloudRelayStatus.error, 'Connect failed: $e');
      _scheduleReconnect();
    }
  }

  /// Manually disconnect cloud relay.
  Future<void> disconnect() async {
    _isManualStop = true;
    _reconnectTimer?.cancel();
    await _disconnectInternal();
    _setStatus(CloudRelayStatus.disconnected, 'Disconnected');
  }

  Future<void> _disconnectInternal() async {
    _heartbeatTimer?.cancel();
    await _sub?.cancel();
    await _channel?.sink.close();
    _channel = null;
    _sub = null;
    await BackgroundRelayService().stopKeepAlive();
  }

  void _scheduleReconnect() {
    if (_isManualStop) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      if (!_isManualStop && _status != CloudRelayStatus.connected) {
        connect();
      }
    });
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 20), (timer) {
      if (_status == CloudRelayStatus.connected && _channel != null) {
        _send({'type': 'ping'});
      }
    });
  }

  void _send(Map<String, dynamic> data) {
    try {
      _channel?.sink.add(jsonEncode(data));
    } catch (e) {
      debugPrint('Failed to send WS message: $e');
    }
  }

  void _onPrinterStatusChanged() {
    if (_status == CloudRelayStatus.connected) {
      _sendPrinterStatus();
    }
  }

  void _sendPrinterStatus() {
    final isOnline = _bleManager?.isConnected ?? false;
    final printerName = _bleManager?.connectedDeviceName ?? 'Thermal Printer';

    _send({
      'type': 'printer_status',
      'status': isOnline ? 'online' : 'offline',
      'printer_online': isOnline,
      'printer_name': isOnline ? printerName : 'Offline',
      'address': _bleManager?.connectedDevice?.remoteId.str ?? '',
      'rssi': 0,
    });
  }

  Future<void> _onMessage(dynamic rawMsg) async {
    try {
      final Map<String, dynamic> msg = jsonDecode(rawMsg as String);
      final String type = (msg['type'] as String? ?? '').toLowerCase();

      switch (type) {
        case 'welcome':
          _assignedGroup = msg['group'] as String? ?? 'Default';
          final clientName = msg['client_name'] as String? ?? 'Terminal';
          _setStatus(
            CloudRelayStatus.connected,
            'Online (Group: $_assignedGroup, Client: $clientName)',
          );
          _sendPrinterStatus();
          unawaited(BackgroundRelayService().startKeepAlive(
            title: 'TinyPOS Cloud Relay Active',
            message: 'Online (Group: $_assignedGroup, Client: $clientName)',
          ));
          break;

        case 'ping':
          _send({'type': 'pong'});
          break;

        case 'print_job':
          await _handlePrintJob(msg);
          break;

        case 'feed_paper':
          try {
            await _bleManager?.feedPaper();
            _send({'type': 'feed_completed'});
          } catch (e) {
            _send({'type': 'feed_failed', 'error': '$e'});
          }
          break;
      }
    } catch (e) {
      debugPrint('Error parsing server message: $e');
    }
  }

  Future<void> _handlePrintJob(Map<String, dynamic> msg) async {
    final String jobId = msg['job_id'] as String? ?? 'unknown';
    final int strength = (msg['strength'] as num?)?.toInt() ?? 4;
    final String imageB64 = msg['image_b64'] as String? ?? '';

    _jobsReceivedCount++;
    notifyListeners();

    // Acknowledge receipt immediately
    _send({'type': 'job_ack', 'job_id': jobId});

    if (imageB64.isEmpty) {
      _send({
        'type': 'job_failed',
        'job_id': jobId,
        'error': 'Empty image payload received',
      });
      return;
    }

    try {
      // Decode Base64 PNG
      final bytes = base64Decode(imageB64);
      final img.Image? decoded = img.decodeImage(bytes);

      if (decoded == null) {
        throw Exception('Failed to decode Base64 receipt image');
      }

      if (_bleManager == null ||
          _bleManager!.status != PrinterConnectionStatus.connected) {
        throw Exception('Local Bluetooth thermal printer is not connected');
      }

      await _bleManager!.printImage(decoded, strength: strength);

      _send({
        'type': 'job_completed',
        'job_id': jobId,
        'message': 'Printed successfully via mobile terminal',
      });
    } catch (e) {
      debugPrint('Print job $jobId failed: $e');
      _send({
        'type': 'job_failed',
        'job_id': jobId,
        'error': '$e',
      });
    }
  }
}
