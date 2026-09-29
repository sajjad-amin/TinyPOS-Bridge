/// Cloud Relay Bridge Screen.
/// Connects mobile device to TinyPOS server via WebSocket and pipes print jobs
/// to the nearby Bluetooth thermal printer.
library;

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/storage_service.dart';
import '../../core/websocket_relay.dart';
import '../../ui/widgets/liquid_glass.dart';

class CloudBridgeScreen extends StatefulWidget {
  final StorageService storage;

  const CloudBridgeScreen({super.key, required this.storage});

  @override
  State<CloudBridgeScreen> createState() => _CloudBridgeScreenState();
}

class _CloudBridgeScreenState extends State<CloudBridgeScreen> {
  final WebSocketRelayService _relay = WebSocketRelayService();

  late final TextEditingController _serverUrlCtrl;
  late final TextEditingController _apiKeyCtrl;
  late final TextEditingController _terminalNameCtrl;

  bool _obscureKey = true;

  @override
  void initState() {
    super.initState();
    _serverUrlCtrl = TextEditingController(text: widget.storage.serverUrl);
    _apiKeyCtrl = TextEditingController(text: widget.storage.clientApiKey);
    _terminalNameCtrl =
        TextEditingController(text: widget.storage.terminalName);
  }

  @override
  void dispose() {
    _serverUrlCtrl.dispose();
    _apiKeyCtrl.dispose();
    _terminalNameCtrl.dispose();
    super.dispose();
  }

  Future<void> _saveAndConnect() async {
    await widget.storage.saveCloudConfig(
      serverUrl: _serverUrlCtrl.text.trim(),
      clientApiKey: _apiKeyCtrl.text.trim(),
      terminalName: _terminalNameCtrl.text.trim(),
    );

    await _relay.connect();
  }

  void _parseAndApplyUrl(String rawUrl) {
    try {
      final uri = Uri.parse(rawUrl.trim());
      String baseUrl = '${uri.scheme}://${uri.host}';
      if (uri.hasPort) {
        baseUrl += ':${uri.port}';
      }

      final key = uri.queryParameters['api_key'] ??
          uri.queryParameters['key'] ??
          '';
      final name = uri.queryParameters['client_name'] ??
          uri.queryParameters['name'] ??
          'Mobile POS';

      setState(() {
        _serverUrlCtrl.text = baseUrl;
        if (key.isNotEmpty) _apiKeyCtrl.text = key;
        if (name.isNotEmpty) _terminalNameCtrl.text = name;
      });

      _saveAndConnect();

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Configuration applied from QR code!')),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Invalid connection QR code: $e')),
      );
    }
  }

  Future<void> _openCameraScanner() async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.black,
      builder: (ctx) {
        return Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.black,
            foregroundColor: Colors.white,
            title: const Text('Scan Server Connect QR'),
            actions: [
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(ctx),
              ),
            ],
          ),
          body: Stack(
            children: [
              MobileScanner(
                onDetect: (capture) {
                  final barcodes = capture.barcodes;
                  for (final barcode in barcodes) {
                    final rawValue = barcode.rawValue;
                    if (rawValue != null && rawValue.isNotEmpty) {
                      Navigator.pop(ctx);
                      _parseAndApplyUrl(rawValue);
                      break;
                    }
                  }
                },
              ),
              Center(
                child: Container(
                  width: 250,
                  height: 250,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.blue, width: 2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
              const Positioned(
                bottom: 40,
                left: 20,
                right: 20,
                child: Text(
                  'Point camera at the Client Connect QR on your TinyPOS Server dashboard',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListenableBuilder(
      listenable: _relay,
      builder: (context, _) {
        final isConnected = _relay.status == CloudRelayStatus.connected;
        final isConnecting = _relay.status == CloudRelayStatus.connecting;

        Color statusColor;
        String statusLabel;

        switch (_relay.status) {
          case CloudRelayStatus.connected:
            statusColor = Colors.green;
            statusLabel = 'Online • Ready to Relay Jobs';
            break;
          case CloudRelayStatus.connecting:
            statusColor = Colors.amber;
            statusLabel = 'Connecting to Cloud Relay...';
            break;
          case CloudRelayStatus.unauthorized:
            statusColor = Colors.red;
            statusLabel = 'Unauthorized (Check API Key)';
            break;
          case CloudRelayStatus.error:
            statusColor = Colors.red;
            statusLabel = _relay.statusMessage ?? 'Connection Error';
            break;
          case CloudRelayStatus.disconnected:
            statusColor = Colors.grey;
            statusLabel = 'Disconnected';
            break;
        }

        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Live Status Card
              LiquidGlass(
                tintColor: statusColor.withAlpha(25),
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(
                              color: statusColor,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            statusLabel,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: statusColor,
                              fontSize: 15,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      if (isConnected) ...[
                        Text(
                          'Assigned Terminal Group: ${_relay.assignedGroup ?? "Default"}',
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Jobs Processed: ${_relay.jobsReceivedCount}',
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.grey.shade600,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          children: [
                            const Icon(Icons.shield_outlined, size: 16, color: Colors.green),
                            const SizedBox(width: 4),
                            Text(
                              'Background & Screen Off Protected',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.green.shade700,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ] else ...[
                        Text(
                          'When connected, print jobs sent from your web POS / cloud server are automatically received and printed.',
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.grey.shade600,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              const SizedBox(height: 14),

              // 1-Click QR Scan Button
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Colors.blue),
                ),
                icon: const Icon(Icons.qr_code_scanner, color: Colors.blue),
                label: const Text(
                  '1-Click Connect (Scan Server QR Code)',
                  style: TextStyle(color: Colors.blue, fontWeight: FontWeight.bold),
                ),
                onPressed: _openCameraScanner,
              ),
              const SizedBox(height: 14),

              // Server Settings Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Cloud Relay Configuration',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),

                      TextField(
                        controller: _serverUrlCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Cloud Server URL',
                          hintText: 'https://your-pos-server.com',
                          prefixIcon: Icon(Icons.cloud_outlined),
                        ),
                      ),
                      const SizedBox(height: 12),

                      TextField(
                        controller: _apiKeyCtrl,
                        obscureText: _obscureKey,
                        decoration: InputDecoration(
                          labelText: 'Client Terminal API Key',
                          hintText: 'sk_client_...',
                          prefixIcon: const Icon(Icons.key_outlined),
                          suffixIcon: IconButton(
                            icon: Icon(
                              _obscureKey
                                  ? Icons.visibility
                                  : Icons.visibility_off,
                            ),
                            onPressed: () {
                              setState(() => _obscureKey = !_obscureKey);
                            },
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),

                      TextField(
                        controller: _terminalNameCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Terminal Name',
                          hintText: 'Mobile Counter 1',
                          prefixIcon: Icon(Icons.smartphone),
                        ),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 18),

              // Connect / Disconnect Action Button
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: isConnected ? Colors.red.shade600 : Colors.blue,
                ),
                icon: isConnecting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2,
                        ),
                      )
                    : Icon(isConnected ? Icons.link_off : Icons.link),
                label: Text(
                  isConnected
                      ? 'Disconnect Cloud Relay'
                      : (isConnecting ? 'Connecting...' : 'Save & Connect to Cloud'),
                ),
                onPressed: isConnecting
                    ? null
                    : (isConnected ? _relay.disconnect : _saveAndConnect),
              ),
            ],
          ),
        );
      },
    );
  }
}
