/// Universal Top Printer Status Bar with connection indicator & quick actions.
library;

import 'package:flutter/material.dart';
import '../../core/ble_printer_manager.dart';
import '../../features/printer_settings/printer_dialog.dart';

class PrinterStatusBar extends StatelessWidget implements PreferredSizeWidget {
  const PrinterStatusBar({super.key});

  @override
  Size get preferredSize => const Size.fromHeight(44);

  @override
  Widget build(BuildContext context) {
    final ble = BlePrinterManager();
    final theme = Theme.of(context);

    return ListenableBuilder(
      listenable: ble,
      builder: (context, _) {
        final isConnected = ble.isConnected;
        final isScanning = ble.isScanning;
        final isPrinting = ble.status == PrinterConnectionStatus.printing;

        Color badgeColor;
        String statusText;

        if (isPrinting) {
          badgeColor = Colors.orange;
          statusText = 'Printing (${(ble.printProgress * 100).toInt()}%)...';
        } else if (isConnected) {
          badgeColor = Colors.green;
          final devName = ble.connectedDeviceName;
          statusText = isScanning ? '$devName (Scanning...)' : devName;
        } else if (isScanning) {
          badgeColor = Colors.amber;
          statusText = 'Scanning for Bluetooth printer...';
        } else {
          badgeColor = Colors.grey;
          statusText = 'No Printer Connected • Tap to Connect';
        }

        final isIOS = Theme.of(context).platform == TargetPlatform.iOS;
        final isDark = theme.brightness == Brightness.dark;

        return Container(
          height: 44,
          decoration: BoxDecoration(
            color: isIOS
                ? (isDark
                    ? const Color(0xFF1E293B).withAlpha(190)
                    : Colors.white.withAlpha(210))
                : theme.colorScheme.surface,
            border: Border(
              bottom: BorderSide(
                color: isDark
                    ? const Color(0xFF334155).withAlpha(120)
                    : const Color(0xFFE2E8F0),
                width: 1.0,
              ),
            ),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            children: [
              // Colored dot indicator
              Container(
                width: 9,
                height: 9,
                decoration: BoxDecoration(
                  color: badgeColor,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 8),

              // Title / Status text (tap to select printer)
              Expanded(
                child: InkWell(
                  onTap: () => PrinterSelectionSheet.show(context),
                  borderRadius: BorderRadius.circular(6),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(
                      statusText,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                        color: isConnected
                            ? (theme.brightness == Brightness.dark
                                ? Colors.white
                                : Colors.black87)
                            : Colors.grey,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ),

              // Quick Feed Paper Icon
              if (isConnected)
                IconButton(
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 34, minHeight: 34),
                  icon: const Icon(Icons.arrow_downward, size: 18),
                  tooltip: 'Feed Paper',
                  onPressed: () async {
                    try {
                      await ble.feedPaper();
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Paper fed successfully!'),
                            duration: Duration(seconds: 1),
                          ),
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

              // Bluetooth Settings Icon
              IconButton(
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 34, minHeight: 34),
                icon: const Icon(Icons.bluetooth, size: 20, color: Colors.blue),
                tooltip: 'Select Printer',
                onPressed: () => PrinterSelectionSheet.show(context),
              ),
            ],
          ),
        );
      },
    );
  }
}
