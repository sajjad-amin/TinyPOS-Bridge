import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:image/image.dart' as img;

import 'bainiu_protocol.dart';
import 'constants.dart';
import 'storage_service.dart';

enum PrinterConnectionStatus {
  disconnected,
  scanning,
  connecting,
  connected,
  printing,
  error,
}

class DiscoveredPrinter {
  final BluetoothDevice device;
  final String name;
  final int rssi;
  final bool isRecommended;

  const DiscoveredPrinter({
    required this.device,
    required this.name,
    required this.rssi,
    this.isRecommended = false,
  });
}

class BlePrinterManager extends ChangeNotifier {
  static final BlePrinterManager _instance = BlePrinterManager._internal();
  factory BlePrinterManager() => _instance;
  BlePrinterManager._internal();

  StorageService? _storage;

  PrinterConnectionStatus _status = PrinterConnectionStatus.disconnected;
  PrinterConnectionStatus get status => _status;

  bool _isScanning = false;
  bool get isScanning => _isScanning;

  bool get isConnected => _connectedDevice != null && _txChar != null;

  BluetoothDevice? _connectedDevice;
  BluetoothDevice? get connectedDevice => _connectedDevice;

  String? _connectedDeviceName;

  /// Human-readable device name. Preserves the advertised name (e.g. "X6")
  /// across restarts even if BluetoothDevice.fromId lacks platformName.
  String get connectedDeviceName {
    if (_connectedDeviceName != null &&
        _connectedDeviceName!.trim().isNotEmpty &&
        _connectedDeviceName != 'Thermal Printer') {
      return _connectedDeviceName!.trim();
    }
    final platName = _connectedDevice?.platformName.trim();
    if (platName != null && platName.isNotEmpty && platName != 'Thermal Printer') {
      return platName;
    }
    final saved = _storage?.savedPrinterName?.trim();
    if (saved != null && saved.isNotEmpty && saved != 'Thermal Printer') {
      return saved;
    }
    return (platName != null && platName.isNotEmpty) ? platName : 'Thermal Printer';
  }

  BluetoothCharacteristic? _txChar;
  int _negotiatedMtu = 23;

  String? _statusMessage;
  String? get statusMessage => _statusMessage;

  double _printProgress = 0.0;
  double get printProgress => _printProgress;

  final List<DiscoveredPrinter> _discoveredPrinters = [];
  List<DiscoveredPrinter> get discoveredPrinters =>
      List.unmodifiable(_discoveredPrinters);

  StreamSubscription? _scanSub;
  StreamSubscription? _connectionStateSub;
  StreamSubscription? _isScanningSub;

  void init(StorageService storage) {
    _storage = storage;
    _isScanningSub?.cancel();
    _isScanningSub = FlutterBluePlus.isScanning.listen((scanning) {
      _isScanning = scanning;
      notifyListeners();
    });
    // Auto-connect to saved printer if bluetooth is enabled
    _tryAutoConnect();
  }

  void _setStatus(PrinterConnectionStatus status, [String? message]) {
    _status = status;
    _statusMessage = message;
    notifyListeners();
  }

  /// Start scanning for nearby thermal printers.
  Future<void> startScan({Duration timeout = const Duration(seconds: 12)}) async {
    if (await FlutterBluePlus.adapterState.first != BluetoothAdapterState.on) {
      if (Platform.isAndroid) {
        try {
          await FlutterBluePlus.turnOn();
        } catch (_) {}
      }
      if (await FlutterBluePlus.adapterState.first != BluetoothAdapterState.on) {
        _setStatus(
          _connectedDevice != null
              ? PrinterConnectionStatus.connected
              : PrinterConnectionStatus.error,
          'Bluetooth is turned off. Please turn on Bluetooth.',
        );
        return;
      }
    }

    _isScanning = true;

    if (_connectedDevice != null) {
      // PRESERVE the active connection! Do not override status to scanning
      final cur = _connectedDevice!;
      final devName = connectedDeviceName;
      _discoveredPrinters.removeWhere((p) => p.device.remoteId != cur.remoteId);
      if (!_discoveredPrinters.any((p) => p.device.remoteId == cur.remoteId)) {
        _discoveredPrinters.insert(0, DiscoveredPrinter(
          device: cur,
          name: devName,
          rssi: -30,
          isRecommended: true,
        ));
      }
      _statusMessage = 'Scanning for other printers...';
      notifyListeners();
    } else {
      _discoveredPrinters.clear();
      _setStatus(PrinterConnectionStatus.scanning, 'Scanning for nearby printers...');
    }

    // 1. Immediately check bonded/paired devices in Android OS Bluetooth settings
    try {
      final bonded = await FlutterBluePlus.bondedDevices;
      for (final device in bonded) {
        final name = device.platformName.trim();
        final displayName = name.isNotEmpty ? name : 'Paired Device';
        final lower = displayName.toLowerCase();
        bool isMatch = false;
        for (final known in kKnownPrinterNames) {
          if (lower.contains(known)) {
            isMatch = true;
            break;
          }
        }
        if (!_discoveredPrinters.any((p) => p.device.remoteId == device.remoteId)) {
          _discoveredPrinters.add(DiscoveredPrinter(
            device: device,
            name: displayName,
            rssi: -50,
            isRecommended: isMatch,
          ));
        }
      }
      if (_discoveredPrinters.isNotEmpty) {
        notifyListeners();
      }
    } catch (_) {}

    await _scanSub?.cancel();
    _scanSub = FlutterBluePlus.onScanResults.listen((results) {
      for (final result in results) {
        final advName = result.advertisementData.advName.trim();
        final platName = result.device.platformName.trim();
        final displayName = advName.isNotEmpty
            ? advName
            : (platName.isNotEmpty ? platName : 'Unknown BLE Device');

        final lowerName = displayName.toLowerCase();

        // Check if device matches known thermal printer names or exposes known services
        bool isMatch = false;
        for (final known in kKnownPrinterNames) {
          if (lowerName.contains(known)) {
            isMatch = true;
            break;
          }
        }

        if (!isMatch && result.advertisementData.serviceUuids.isNotEmpty) {
          for (final uuid in result.advertisementData.serviceUuids) {
            final uuidStr = uuid.toString().toLowerCase();
            for (final knownService in kKnownServiceUuids) {
              if (uuidStr.contains(knownService)) {
                isMatch = true;
                break;
              }
            }
          }
        }

        final index = _discoveredPrinters.indexWhere(
          (p) => p.device.remoteId == result.device.remoteId,
        );

        final printer = DiscoveredPrinter(
          device: result.device,
          name: displayName,
          rssi: result.rssi,
          isRecommended: isMatch,
        );

        if (index >= 0) {
          if (_connectedDevice?.remoteId == result.device.remoteId) {
            if (displayName.isNotEmpty && displayName != 'Thermal Printer') {
              _connectedDeviceName = displayName;
              _storage?.savePrinter(id: result.device.remoteId.str, name: displayName);
            }
            _discoveredPrinters[index] = DiscoveredPrinter(
              device: result.device,
              name: displayName,
              rssi: result.rssi,
              isRecommended: true,
            );
          } else {
            _discoveredPrinters[index] = printer;
          }
        } else {
          _discoveredPrinters.add(printer);
        }

        // Sort: Connected device first, then recommended printers, then signal strength
        _discoveredPrinters.sort((a, b) {
          final isAConnected = _connectedDevice?.remoteId == a.device.remoteId;
          final isBConnected = _connectedDevice?.remoteId == b.device.remoteId;
          if (isAConnected) return -1;
          if (isBConnected) return 1;
          if (a.isRecommended && !b.isRecommended) return -1;
          if (!a.isRecommended && b.isRecommended) return 1;
          return b.rssi.compareTo(a.rssi);
        });

        notifyListeners();
      }
    });

    try {
      await FlutterBluePlus.startScan(
        timeout: timeout,
        androidUsesFineLocation: true,
      );
    } catch (e) {
      _setStatus(
        _connectedDevice != null
            ? PrinterConnectionStatus.connected
            : PrinterConnectionStatus.error,
        'Scan failed: $e. Make sure Location (GPS) and Bluetooth are ON.',
      );
    } finally {
      _isScanning = false;
      if (_connectedDevice != null) {
        _setStatus(PrinterConnectionStatus.connected);
      } else if (_status == PrinterConnectionStatus.scanning) {
        _setStatus(PrinterConnectionStatus.disconnected);
      }
    }
  }

  /// Stop active BLE scanning immediately.
  Future<void> stopScan() async {
    _isScanning = false;
    await FlutterBluePlus.stopScan();
    await _scanSub?.cancel();
    if (_connectedDevice != null) {
      _setStatus(
        PrinterConnectionStatus.connected,
        'Connected to ${_connectedDevice!.platformName}',
      );
    } else {
      _setStatus(PrinterConnectionStatus.disconnected);
    }
  }

  /// Connect to a specific thermal printer device.
  Future<bool> connect(BluetoothDevice device, {String? name}) async {
    if (_connectedDevice?.remoteId == device.remoteId && _txChar != null) {
      _setStatus(PrinterConnectionStatus.connected, 'Already connected');
      return true;
    }

    await stopScan();
    final String initialName = (name != null && name.trim().isNotEmpty)
        ? name.trim()
        : (device.platformName.trim().isNotEmpty
            ? device.platformName.trim()
            : (_storage?.savedPrinterName?.trim().isNotEmpty == true
                ? _storage!.savedPrinterName!.trim()
                : 'Thermal Printer'));

    _setStatus(
      PrinterConnectionStatus.connecting,
      'Connecting to $initialName...',
    );

    try {
      if (_connectedDevice != null && _connectedDevice?.remoteId != device.remoteId) {
        await _connectedDevice?.disconnect();
      }
      await _connectionStateSub?.cancel();

      await device.connect(
        timeout: const Duration(seconds: 12),
        autoConnect: false,
      );

      _connectedDevice = device;

      // Listen to connection state changes
      _connectionStateSub = device.connectionState.listen((state) {
        if (state == BluetoothConnectionState.disconnected) {
          _connectedDevice = null;
          _connectedDeviceName = null;
          _txChar = null;
          _setStatus(
            PrinterConnectionStatus.disconnected,
            'Printer disconnected',
          );
        }
      });

      // Request maximum possible MTU for faster transmission
      try {
        _negotiatedMtu = await device.requestMtu(512);
      } catch (_) {
        _negotiatedMtu = 23;
      }

      // Discover services and find the TX characteristic
      final services = await device.discoverServices();
      BluetoothCharacteristic? foundTx;

      for (final service in services) {
        final sUuid = service.uuid.toString().toLowerCase();
        for (final char in service.characteristics) {
          final cUuid = char.uuid.toString().toLowerCase();

          // 1. Direct match on known TX UUIDs
          for (final knownTx in kKnownTxCharUuids) {
            if (cUuid.contains(knownTx)) {
              foundTx = char;
              break;
            }
          }
          if (foundTx != null) break;

          // 2. Fallback: match on known service and writable characteristic
          for (final knownSvc in kKnownServiceUuids) {
            if (sUuid.contains(knownSvc) &&
                (char.properties.write ||
                    char.properties.writeWithoutResponse)) {
              foundTx = char;
              break;
            }
          }
          if (foundTx != null) break;
        }
        if (foundTx != null) break;
      }

      // 3. Absolute fallback: first writable characteristic found
      if (foundTx == null) {
        for (final service in services) {
          for (final char in service.characteristics) {
            if (char.properties.write || char.properties.writeWithoutResponse) {
              foundTx = char;
              break;
            }
          }
          if (foundTx != null) break;
        }
      }

      if (foundTx == null) {
        throw Exception('No writable thermal printer characteristic found');
      }

      _txChar = foundTx;

      // Determine best human-readable device name without degrading "X6" to "Thermal Printer"
      String devName;
      final explicitName = name?.trim();
      final platName = device.platformName.trim();
      final savedName = _storage?.savedPrinterName?.trim();

      if (explicitName != null && explicitName.isNotEmpty && explicitName != 'Thermal Printer') {
        devName = explicitName;
      } else if (platName.isNotEmpty && platName != 'Thermal Printer') {
        devName = platName;
      } else if (savedName != null && savedName.isNotEmpty && savedName != 'Thermal Printer') {
        devName = savedName;
      } else if (platName.isNotEmpty) {
        devName = platName;
      } else {
        devName = 'Thermal Printer';
      }

      _connectedDeviceName = devName;
      await _storage?.savePrinter(id: device.remoteId.str, name: devName);

      _setStatus(
        PrinterConnectionStatus.connected,
        'Connected to $devName',
      );
      return true;
    } catch (e) {
      _setStatus(PrinterConnectionStatus.error, 'Connection failed: $e');
      return false;
    }
  }

  /// Disconnect current printer.
  Future<void> disconnect() async {
    await _connectionStateSub?.cancel();
    await _connectedDevice?.disconnect();
    _connectedDevice = null;
    _connectedDeviceName = null;
    _txChar = null;
    _setStatus(PrinterConnectionStatus.disconnected, 'Disconnected');
  }

  /// Attempt auto-connection to saved printer.
  Future<void> _tryAutoConnect() async {
    final savedId = _storage?.savedPrinterId;
    final savedName = _storage?.savedPrinterName;
    if (savedId == null || savedId.isEmpty) return;

    if (await FlutterBluePlus.adapterState.first != BluetoothAdapterState.on) {
      return;
    }

    try {
      final device = BluetoothDevice.fromId(savedId);
      await connect(device, name: savedName);
    } catch (e) {
      debugPrint('Auto-connect to $savedId failed: $e');
    }
  }

  /// Send raw packet bytes through TX characteristic with MTU chunking.
  Future<void> _writeBytes(Uint8List bytes) async {
    if (_txChar == null) {
      throw Exception('Printer is not connected or TX characteristic missing');
    }

    // Usable payload per write is MTU - 3
    final int chunkSize = (_negotiatedMtu - 3).clamp(20, 240);
    final bool withoutResponse = _txChar!.properties.writeWithoutResponse;

    if (bytes.length <= chunkSize) {
      await _txChar!.write(bytes, withoutResponse: withoutResponse);
      return;
    }

    for (int offset = 0; offset < bytes.length; offset += chunkSize) {
      final int end = (offset + chunkSize < bytes.length)
          ? offset + chunkSize
          : bytes.length;
      final chunk = bytes.sublist(offset, end);

      await _txChar!.write(chunk, withoutResponse: withoutResponse);
      if (end < bytes.length) {
        await Future.delayed(const Duration(milliseconds: 2));
      }
    }
  }

  /// Trigger paper feed command.
  Future<void> feedPaper() async {
    if (!isConnected) {
      throw Exception('Printer not connected');
    }
    await _writeBytes(kCmdFeedPaper);
  }

  /// Print a rendered thermal image with progress updates.
  Future<void> printImage(
    img.Image image, {
    int strength = 4,
    Function(double progress)? onProgress,
  }) async {
    if (!isConnected || _txChar == null) {
      throw Exception('Printer is not connected');
    }

    _setStatus(PrinterConnectionStatus.printing, 'Printing receipt...');
    _printProgress = 0.0;
    notifyListeners();

    try {
      final params = getStrengthParams(strength);
      final rows = encodeImageToLsbRows(image, threshold: params.threshold);

      // 1. Send initialization sequence
      await _writeBytes(kCmdSetQuality200Dpi);
      await Future.delayed(const Duration(milliseconds: 20));

      await _writeBytes(makeEnergyPacket(params.energy));
      await Future.delayed(const Duration(milliseconds: 20));

      await _writeBytes(kCmdApplyEnergy);
      await Future.delayed(const Duration(milliseconds: 20));

      await _writeBytes(kCmdSetSpeed);
      await Future.delayed(const Duration(milliseconds: 20));

      await _writeBytes(kCmdLatticeStart);
      await Future.delayed(const Duration(milliseconds: 30));

      // 2. Stream LSB rows with thermal pacing
      final int totalRows = rows.length;
      for (int i = 0; i < totalRows; i++) {
        // Bainiu print row command 0xA2
        final rowPacket = makePacket(0xA2, rows[i]);
        await _writeBytes(rowPacket);

        // Throttle progress updates to avoid flooding UI thread (every 10 rows or on last row)
        if (i % 10 == 0 || i == totalRows - 1) {
          _printProgress = (i + 1) / totalRows;
          onProgress?.call(_printProgress);
          notifyListeners();
        }

        // Pacing delay between thermal rows to allow print head cooling/movement
        if (params.rowDelay.inMilliseconds > 0) {
          await Future.delayed(params.rowDelay);
        }
      }

      // 3. Send lattice end & paper feed
      await _writeBytes(kCmdLatticeEnd);
      await Future.delayed(const Duration(milliseconds: 30));

      await _writeBytes(kCmdFeedPaper);
      await Future.delayed(const Duration(milliseconds: 50));

      _setStatus(PrinterConnectionStatus.connected, 'Print complete!');
    } catch (e) {
      _setStatus(PrinterConnectionStatus.error, 'Print failed: $e');
      rethrow;
    } finally {
      _printProgress = 0.0;
      notifyListeners();
    }
  }
}
