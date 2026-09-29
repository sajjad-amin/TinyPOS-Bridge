import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../../core/ble_printer_manager.dart';

class PrinterSelectionSheet extends StatefulWidget {
  const PrinterSelectionSheet({super.key});

  static Future<void> show(BuildContext context) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => const PrinterSelectionSheet(),
    );
  }

  @override
  State<PrinterSelectionSheet> createState() => _PrinterSelectionSheetState();
}

class _PrinterSelectionSheetState extends State<PrinterSelectionSheet> {
  final BlePrinterManager _ble = BlePrinterManager();

  @override
  void initState() {
    super.initState();
    // Only start scan automatically if no printer is currently connected
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_ble.isConnected) {
        _ble.startScan();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isIOS = defaultTargetPlatform == TargetPlatform.iOS;
    final isDark = theme.brightness == Brightness.dark;

    return ListenableBuilder(
      listenable: _ble,
      builder: (context, _) {
        final isScanning = _ble.isScanning;
        final isConnected = _ble.isConnected;
        final connectedDev = _ble.connectedDevice;
        final list = _ble.discoveredPrinters;

        final sheetContent = Container(
          decoration: BoxDecoration(
            color: isIOS
                ? (isDark
                    ? const Color(0xFF0F172A).withAlpha(205)
                    : Colors.white.withAlpha(225))
                : theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            border: isIOS
                ? Border(
                    top: BorderSide(
                      color: isDark
                          ? Colors.white.withAlpha(35)
                          : Colors.white.withAlpha(160),
                      width: 1.2,
                    ),
                  )
                : null,
          ),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.75,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Drag handle
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: Colors.grey.withAlpha(80),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              // Title and Scan / Stop action
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.bluetooth, color: Colors.blue),
                      const SizedBox(width: 8),
                      Text(
                        'Bluetooth Printers',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  if (isScanning)
                    FilledButton.tonalIcon(
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.red.withAlpha(30),
                        foregroundColor: Colors.red,
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      ),
                      icon: const Icon(Icons.stop_circle_outlined, size: 16),
                      label: const Text(
                        'Stop Scan',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
                      ),
                      onPressed: () => _ble.stopScan(),
                    )
                  else
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      ),
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text('Scan', style: TextStyle(fontSize: 12)),
                      onPressed: () => _ble.startScan(),
                    ),
                ],
              ),
              const Divider(),

              // Status / Permission / Location Alert Banner
              if (_ble.statusMessage != null &&
                  _ble.statusMessage!.isNotEmpty &&
                  !isConnected) ...[
                Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.amber.withAlpha(30),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.amber.shade700),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline,
                          color: Colors.amber.shade900, size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _ble.statusMessage!,
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.amber.shade900,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Connected Device Banner
              if (isConnected && connectedDev != null) ...[
                Card(
                  color: Colors.green.withAlpha(25),
                  child: ListTile(
                    leading: const CircleAvatar(
                      backgroundColor: Colors.green,
                      foregroundColor: Colors.white,
                      child: Icon(Icons.print, size: 20),
                    ),
                    title: Text(
                      _ble.connectedDeviceName,
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    subtitle: Text(
                      'Connected • ${connectedDev.remoteId.str}',
                      style: const TextStyle(fontSize: 12),
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.arrow_downward, color: Colors.green),
                          tooltip: 'Feed Paper',
                          onPressed: () => _ble.feedPaper(),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close, color: Colors.red),
                          tooltip: 'Disconnect',
                          onPressed: () => _ble.disconnect(),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 8),
              ],

              // Discovered Printers List
              Expanded(
                child: list.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                isScanning ? Icons.bluetooth_searching : Icons.print_disabled,
                                size: 40,
                                color: Colors.grey,
                              ),
                              const SizedBox(height: 10),
                              Text(
                                isScanning
                                    ? 'Scanning nearby Bluetooth printers...'
                                    : 'No printers found.\nMake sure printer power is on and Location/GPS is enabled.',
                                textAlign: TextAlign.center,
                                style: const TextStyle(color: Colors.grey),
                              ),
                              if (!isScanning) ...[
                                const SizedBox(height: 12),
                                OutlinedButton.icon(
                                  icon: const Icon(Icons.refresh),
                                  label: const Text('Try Scan Again'),
                                  onPressed: () => _ble.startScan(),
                                ),
                              ],
                            ],
                          ),
                        ),
                      )
                    : ListView.builder(
                        itemCount: list.length,
                        itemBuilder: (context, index) {
                          final item = list[index];
                          final isThisConnected = connectedDev?.remoteId ==
                              item.device.remoteId;

                          return Card(
                            margin: const EdgeInsets.symmetric(vertical: 4),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: item.isRecommended
                                    ? Colors.green.withAlpha(30)
                                    : Colors.blue.withAlpha(20),
                                foregroundColor: item.isRecommended
                                    ? Colors.green
                                    : Colors.blue,
                                child: Icon(
                                  item.isRecommended
                                      ? Icons.print
                                      : Icons.bluetooth,
                                  size: 20,
                                ),
                              ),
                              title: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      item.name,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                      ),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                  if (item.isRecommended)
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 6,
                                        vertical: 2,
                                      ),
                                      decoration: BoxDecoration(
                                        color: Colors.green.withAlpha(30),
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: const Text(
                                        'Thermal',
                                        style: TextStyle(
                                          fontSize: 10,
                                          color: Colors.green,
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                              subtitle: Text(
                                '${item.device.remoteId.str} • RSSI: ${item.rssi} dBm',
                                style: const TextStyle(fontSize: 12),
                              ),
                              trailing: isThisConnected
                                  ? const Text(
                                      'Active',
                                      style: TextStyle(
                                        color: Colors.green,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    )
                                  : ElevatedButton(
                                      style: ElevatedButton.styleFrom(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 14,
                                          vertical: 6,
                                        ),
                                        textStyle: const TextStyle(fontSize: 12),
                                      ),
                                      onPressed: () => _ble.connect(item.device, name: item.name),
                                      child: const Text('Connect'),
                                    ),
                            ),
                          );
                        },
                      ),
              ),

              const SizedBox(height: 12),
              // Bottom paper feed action button
              if (isConnected)
                OutlinedButton.icon(
                  icon: const Icon(Icons.arrow_downward),
                  label: const Text('📄 Feed Paper (Test Tear Line)'),
                  onPressed: () async {
                    try {
                      await _ble.feedPaper();
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Paper fed successfully!')),
                        );
                      }
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Feed failed: $e')),
                        );
                      }
                    }
                  },
                ),
            ],
          ),
        );

        if (isIOS) {
          return ClipRRect(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 25, sigmaY: 25),
              child: sheetContent,
            ),
          );
        }

        return sheetContent;
      },
    );
  }
}
