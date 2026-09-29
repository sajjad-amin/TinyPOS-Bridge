/// QR Code Generator & Thermal Print Screen.
/// Supports URL, Wi-Fi configuration barcodes, Plain Text, plus optional Header/Footer.
library;

import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import '../../core/ble_printer_manager.dart';
import '../../engine/qr_rasterizer.dart';
import '../../ui/widgets/liquid_glass.dart';
import '../printer_settings/printer_dialog.dart';

class QrPrintScreen extends StatefulWidget {
  const QrPrintScreen({super.key});

  @override
  State<QrPrintScreen> createState() => _QrPrintScreenState();
}

class _QrPrintScreenState extends State<QrPrintScreen> {
  final BlePrinterManager _ble = BlePrinterManager();

  int _selectedModeIndex = 0; // 0: URL, 1: Wi-Fi, 2: Plain Text

  final TextEditingController _urlCtrl = TextEditingController(text: 'https://');
  final TextEditingController _ssidCtrl = TextEditingController();
  final TextEditingController _wifiPassCtrl = TextEditingController();
  String _wifiAuth = 'WPA';
  bool _wifiHidden = false;

  final TextEditingController _plainTextCtrl = TextEditingController();
  final TextEditingController _headerCtrl = TextEditingController();
  final TextEditingController _footerCtrl = TextEditingController();

  double _qrSize = 260.0;
  int _strength = 4;
  bool _isPrinting = false;
  bool _isPreviewing = false;

  @override
  void dispose() {
    _urlCtrl.dispose();
    _ssidCtrl.dispose();
    _wifiPassCtrl.dispose();
    _plainTextCtrl.dispose();
    _headerCtrl.dispose();
    _footerCtrl.dispose();
    super.dispose();
  }

  String _buildQrPayload() {
    switch (_selectedModeIndex) {
      case 1: // Wi-Fi
        return QrPrintPayload.formatWifi(
          ssid: _ssidCtrl.text.trim(),
          password: _wifiPassCtrl.text,
          authType: _wifiAuth,
          isHidden: _wifiHidden,
        );
      case 2: // Plain text
        return _plainTextCtrl.text.trim();
      case 0: // URL
      default:
        return _urlCtrl.text.trim();
    }
  }

  void _resetQrSettings() {
    setState(() {
      _qrSize = 260.0;
      _strength = 4;
      _headerCtrl.clear();
      _footerCtrl.clear();
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('QR settings reset to defaults (260px, Normal Darkness)'),
          duration: Duration(seconds: 1),
        ),
      );
    }
  }

  Future<void> _showBitmapPreview() async {
    final qrData = _buildQrPayload();
    if (qrData.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter QR code content to preview')),
      );
      return;
    }

    setState(() => _isPreviewing = true);

    try {
      final payload = QrPrintPayload(
        qrContent: qrData,
        headerText: _headerCtrl.text.trim().isNotEmpty ? _headerCtrl.text.trim() : null,
        footerText: _footerCtrl.text.trim().isNotEmpty ? _footerCtrl.text.trim() : null,
        qrSize: _qrSize,
      );

      final bitmap = await renderQrToBitmap(payload);
      final pngBytes = Uint8List.fromList(img.encodePng(bitmap));

      if (!mounted) return;

      showDialog(
        context: context,
        builder: (ctx) {
          return Dialog(
            backgroundColor: Colors.grey.shade900,
            insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '384px Thermal QR Preview',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                          ),
                          Text(
                            '${bitmap.width} × ${bitmap.height} dots • 1-bit monochrome',
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, color: Colors.white),
                        onPressed: () => Navigator.pop(ctx),
                      ),
                    ],
                  ),
                ),
                const Divider(color: Colors.white24, height: 1),
                Flexible(
                  child: Container(
                    color: const Color(0xFF141414),
                    constraints: const BoxConstraints(maxHeight: 460),
                    child: InteractiveViewer(
                      minScale: 0.5,
                      maxScale: 6.0,
                      child: Center(
                        child: Container(
                          margin: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withAlpha(120),
                                blurRadius: 10,
                                spreadRadius: 2,
                              ),
                            ],
                          ),
                          child: Image.memory(
                            pngBytes,
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.none,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                const Divider(color: Colors.white24, height: 1),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Pinch to zoom thermal dots',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                      ),
                      FilledButton.icon(
                        style: FilledButton.styleFrom(
                          visualDensity: VisualDensity.compact,
                        ),
                        icon: const Icon(Icons.print, size: 16),
                        label: const Text('Print Now'),
                        onPressed: () {
                          Navigator.pop(ctx);
                          _handlePrint();
                        },
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Preview error: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isPreviewing = false);
      }
    }
  }

  Future<void> _handlePrint() async {
    final qrData = _buildQrPayload();
    if (qrData.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter QR code content')),
      );
      return;
    }

    if (!_ble.isConnected) {
      PrinterSelectionSheet.show(context);
      return;
    }

    setState(() => _isPrinting = true);

    try {
      final payload = QrPrintPayload(
        qrContent: qrData,
        headerText: _headerCtrl.text.trim().isNotEmpty ? _headerCtrl.text.trim() : null,
        footerText: _footerCtrl.text.trim().isNotEmpty ? _footerCtrl.text.trim() : null,
        qrSize: _qrSize,
      );

      final bitmap = await renderQrToBitmap(payload);
      await _ble.printImage(bitmap, strength: _strength);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('QR Code printed successfully!')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Print failed: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isPrinting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListenableBuilder(
      listenable: _ble,
      builder: (context, _) {
        final isConnected = _ble.isConnected;

        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // QR Mode Segmented Switch
              SegmentedButton<int>(
                segments: const [
                  ButtonSegment(
                    value: 0,
                    icon: Icon(Icons.link, size: 18),
                    label: Text('Web URL'),
                  ),
                  ButtonSegment(
                    value: 1,
                    icon: Icon(Icons.wifi, size: 18),
                    label: Text('Wi-Fi'),
                  ),
                  ButtonSegment(
                    value: 2,
                    icon: Icon(Icons.notes, size: 18),
                    label: Text('Plain Text'),
                  ),
                ],
                selected: {_selectedModeIndex},
                onSelectionChanged: (val) {
                  setState(() => _selectedModeIndex = val.first);
                },
              ),
              const SizedBox(height: 12),

              // Content Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_selectedModeIndex == 0) ...[
                        // URL Input
                        const Text(
                          'Target Web URL:',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _urlCtrl,
                          keyboardType: TextInputType.url,
                          decoration: const InputDecoration(
                            hintText: 'https://your-store.com/menu',
                            prefixIcon: Icon(Icons.link),
                          ),
                        ),
                      ] else if (_selectedModeIndex == 1) ...[
                        // Wi-Fi Inputs
                        const Text(
                          'Wi-Fi Network Credentials:',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _ssidCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Network Name (SSID)',
                            prefixIcon: Icon(Icons.wifi),
                          ),
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _wifiPassCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Password',
                            prefixIcon: Icon(Icons.lock_outline),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                initialValue: _wifiAuth,
                                isExpanded: true,
                                decoration: const InputDecoration(
                                  labelText: 'Security',
                                  isDense: true,
                                ),
                                items: const [
                                  DropdownMenuItem(
                                    value: 'WPA',
                                    child: Text('WPA / WPA2 / WPA3 (Standard)'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'WEP',
                                    child: Text('WEP (Legacy)'),
                                  ),
                                  DropdownMenuItem(
                                    value: 'NONE',
                                    child: Text('None (Open Network)'),
                                  ),
                                ],
                                onChanged: (val) {
                                  if (val != null) setState(() => _wifiAuth = val);
                                },
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: CheckboxListTile(
                                contentPadding: EdgeInsets.zero,
                                title: const Text('Hidden', style: TextStyle(fontSize: 13)),
                                value: _wifiHidden,
                                onChanged: (val) => setState(() => _wifiHidden = val ?? false),
                              ),
                            ),
                          ],
                        ),
                      ] else ...[
                        // Plain Text
                        const Text(
                          'Raw Text Content:',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _plainTextCtrl,
                          maxLines: 4,
                          decoration: const InputDecoration(
                            hintText: 'Enter text, serial number, or data string...',
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              const SizedBox(height: 12),

              // Layout, Sizing & Print Quality Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Layout, Sizing & Quality',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.refresh, size: 20),
                            tooltip: 'Reset QR size & options to default',
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                            onPressed: _resetQrSettings,
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      // QR Size Slider
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'QR Code Dimension:',
                            style: TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.blue.withAlpha(30),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              '${_qrSize.toInt()} dots',
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.blue,
                              ),
                            ),
                          ),
                        ],
                      ),
                      Slider(
                        value: _qrSize,
                        min: 160.0,
                        max: 360.0,
                        divisions: 20,
                        label: '${_qrSize.toInt()} dots',
                        onChanged: (val) => setState(() => _qrSize = val),
                      ),
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        children: [
                          ChoiceChip(
                            label: const Text('Compact (180)'),
                            selected: (_qrSize - 180.0).abs() < 1.0,
                            onSelected: (_) => setState(() => _qrSize = 180.0),
                          ),
                          ChoiceChip(
                            label: const Text('Standard (260)'),
                            selected: (_qrSize - 260.0).abs() < 1.0,
                            onSelected: (_) => setState(() => _qrSize = 260.0),
                          ),
                          ChoiceChip(
                            label: const Text('Large (320)'),
                            selected: (_qrSize - 320.0).abs() < 1.0,
                            onSelected: (_) => setState(() => _qrSize = 320.0),
                          ),
                          ChoiceChip(
                            label: const Text('Full (360)'),
                            selected: (_qrSize - 360.0).abs() < 1.0,
                            onSelected: (_) => setState(() => _qrSize = 360.0),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),

                      TextField(
                        controller: _headerCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Header Text (Printed Above QR)',
                          hintText: 'e.g. Scan to Connect to Wi-Fi',
                          isDense: true,
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _footerCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Footer Text (Printed Below QR)',
                          hintText: 'e.g. Password: GuestPassword123',
                          isDense: true,
                        ),
                      ),
                      const SizedBox(height: 10),
                      DropdownButtonFormField<int>(
                        initialValue: _strength,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Print Darkness',
                          isDense: true,
                        ),
                        items: const [
                          DropdownMenuItem(value: 1, child: Text('1 - Lightest')),
                          DropdownMenuItem(value: 2, child: Text('2 - Light')),
                          DropdownMenuItem(value: 3, child: Text('3 - Medium')),
                          DropdownMenuItem(value: 4, child: Text('4 - Normal')),
                          DropdownMenuItem(value: 5, child: Text('5 - Dark')),
                          DropdownMenuItem(value: 6, child: Text('6 - Very Dark')),
                          DropdownMenuItem(value: 7, child: Text('7 - Max Dark')),
                        ],
                        onChanged: (val) {
                          if (val != null) setState(() => _strength = val);
                        },
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 18),

              // Action Buttons: Preview Bitmap & Print
              Row(
                children: [
                  Expanded(
                    flex: 4,
                    child: OutlinedButton.icon(
                      icon: _isPreviewing
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.visibility_outlined, size: 18),
                      label: const Text('Preview', maxLines: 1),
                      onPressed: _isPrinting ? null : _showBitmapPreview,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    flex: 6,
                    child: ElevatedButton.icon(
                      icon: _isPrinting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              ),
                            )
                          : const Icon(Icons.qr_code, size: 18),
                      label: Text(_isPrinting ? 'Printing QR...' : 'Print QR Code', maxLines: 1),
                      onPressed: _isPrinting ? null : _handlePrint,
                    ),
                  ),
                ],
              ),

              if (!isConnected) ...[
                const SizedBox(height: 8),
                Text(
                  '⚠️ Thermal printer not connected. Tap button above to pair.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: theme.colorScheme.error,
                    fontSize: 12,
                  ),
                ),
              ],
              const SizedBox(height: 28),
            ],
          ),
        );
      },
    );
  }
}
