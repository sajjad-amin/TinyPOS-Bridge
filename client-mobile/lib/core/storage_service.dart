/// Local storage service for persistent printer selection and cloud settings.
library;

import 'package:shared_preferences/shared_preferences.dart';

class StorageService {
  static const String _kKeyPrinterId = 'saved_printer_id';
  static const String _kKeyPrinterName = 'saved_printer_name';
  static const String _kKeyServerUrl = 'server_url';
  static const String _kKeyApiKey = 'client_api_key';
  static const String _kKeyTerminalName = 'terminal_name';
  static const String _kKeyStrength = 'default_strength';

  final SharedPreferences _prefs;

  StorageService(this._prefs);

  static Future<StorageService> init() async {
    final prefs = await SharedPreferences.getInstance();
    return StorageService(prefs);
  }

  // --- Printer ---
  String? get savedPrinterId => _prefs.getString(_kKeyPrinterId);
  String? get savedPrinterName => _prefs.getString(_kKeyPrinterName);

  Future<void> savePrinter({required String id, required String name}) async {
    await _prefs.setString(_kKeyPrinterId, id);
    await _prefs.setString(_kKeyPrinterName, name);
  }

  Future<void> clearPrinter() async {
    await _prefs.remove(_kKeyPrinterId);
    await _prefs.remove(_kKeyPrinterName);
  }

  // --- Cloud Server Relay ---
  String get serverUrl =>
      _prefs.getString(_kKeyServerUrl) ?? 'wss://your-pos-server.com';

  String get clientApiKey => _prefs.getString(_kKeyApiKey) ?? '';

  String get terminalName =>
      _prefs.getString(_kKeyTerminalName) ?? 'Mobile Terminal';

  Future<void> saveCloudConfig({
    required String serverUrl,
    required String clientApiKey,
    required String terminalName,
  }) async {
    await _prefs.setString(_kKeyServerUrl, serverUrl.trim());
    await _prefs.setString(_kKeyApiKey, clientApiKey.trim());
    await _prefs.setString(_kKeyTerminalName, terminalName.trim());
  }

  // --- Strength ---
  int get defaultStrength => _prefs.getInt(_kKeyStrength) ?? 4;

  Future<void> setStrength(int val) async {
    await _prefs.setInt(_kKeyStrength, val.clamp(1, 7));
  }
}
