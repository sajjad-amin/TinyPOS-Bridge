/// Background Relay & Keep-Alive Service.
/// Keeps WebSocket Relay and Bluetooth connections active when the app
/// is minimized, switched away, or when the screen is turned off.
/// - iOS: Uses AVAudioSession (.playback + .mixWithOthers) + silent audio loop.
/// - Android: Uses a sticky Foreground Service with WakeLock.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class BackgroundRelayService {
  static const MethodChannel _channel =
      MethodChannel('com.sajjadamin.tinypos/background_relay');

  static final BackgroundRelayService _instance =
      BackgroundRelayService._internal();
  factory BackgroundRelayService() => _instance;
  BackgroundRelayService._internal();

  bool _isActive = false;
  bool get isActive => _isActive;

  /// Start background execution keep-alive.
  Future<void> startKeepAlive({
    String title = 'TinyPOS Cloud Relay Active',
    String message = 'Terminal online • Ready for thermal print jobs',
  }) async {
    // Only supported on mobile platforms
    if (kIsWeb) return;

    try {
      final success = await _channel.invokeMethod<bool>('startKeepAlive', {
        'title': title,
        'message': message,
      });
      _isActive = success ?? true;
      debugPrint('[BackgroundRelayService] Keep-alive started: $_isActive');
    } catch (e) {
      debugPrint('[BackgroundRelayService] Failed to start keep-alive: $e');
    }
  }

  /// Stop background execution keep-alive.
  Future<void> stopKeepAlive() async {
    if (kIsWeb) return;

    try {
      await _channel.invokeMethod<bool>('stopKeepAlive');
      _isActive = false;
      debugPrint('[BackgroundRelayService] Keep-alive stopped');
    } catch (e) {
      debugPrint('[BackgroundRelayService] Failed to stop keep-alive: $e');
    }
  }

  /// Check if keep-alive is currently active on the native side.
  Future<bool> checkActiveStatus() async {
    if (kIsWeb) return false;

    try {
      final active = await _channel.invokeMethod<bool>('isKeepAliveActive');
      _isActive = active ?? false;
      return _isActive;
    } catch (_) {
      return false;
    }
  }
}
