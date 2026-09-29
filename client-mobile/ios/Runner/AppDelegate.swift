import Flutter
import UIKit
import AVFoundation

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  private var audioPlayer: AVAudioPlayer?
  private var backgroundTask: UIBackgroundTaskIdentifier = .invalid
  private var isKeepAliveActive = false

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    let result = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    if let controller = window?.rootViewController as? FlutterViewController {
      setupBackgroundChannel(binaryMessenger: controller.binaryMessenger)
    }
    return result
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "BackgroundRelay") {
      setupBackgroundChannel(binaryMessenger: registrar.messenger())
    }
  }

  private func setupBackgroundChannel(binaryMessenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.sajjadamin.tinypos/background_relay",
      binaryMessenger: binaryMessenger
    )
    channel.setMethodCallHandler { [weak self] (call, result) in
      guard let self = self else { return }
      switch call.method {
      case "startKeepAlive":
        self.startKeepAlive()
        result(true)
      case "stopKeepAlive":
        self.stopKeepAlive()
        result(true)
      case "isKeepAliveActive":
        result(self.isKeepAliveActive)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func startKeepAlive() {
    guard !isKeepAliveActive else { return }
    isKeepAliveActive = true

    do {
      let session = AVAudioSession.sharedInstance()
      try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
      try session.setActive(true)

      let silentWavData = generateSilentWav()
      audioPlayer = try AVAudioPlayer(data: silentWavData)
      audioPlayer?.numberOfLoops = -1 // Infinite background loop
      audioPlayer?.volume = 0.0 // Digital zero volume
      audioPlayer?.play()
      print("[TinyPOS] Background keep-alive activated (AVAudioSession.playback with mixWithOthers)")
    } catch {
      print("[TinyPOS] Failed to start background audio keep-alive: \(error)")
    }

    beginBgTask()
  }

  private func stopKeepAlive() {
    guard isKeepAliveActive else { return }
    isKeepAliveActive = false

    audioPlayer?.stop()
    audioPlayer = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    endBgTask()
    print("[TinyPOS] Background keep-alive stopped")
  }

  private func beginBgTask() {
    if backgroundTask == .invalid {
      backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "TinyPOSRelay") { [weak self] in
        self?.endBgTask()
      }
    }
  }

  private func endBgTask() {
    if backgroundTask != .invalid {
      UIApplication.shared.endBackgroundTask(backgroundTask)
      backgroundTask = .invalid
    }
  }

  /// Generates 1-second 8000Hz 8-bit mono PCM digital silence in WAV format
  private func generateSilentWav() -> Data {
    let sampleRate: UInt32 = 8000
    let numSamples: UInt32 = 8000
    let subchunk2Size = numSamples // 8-bit mono = 1 byte per sample
    let chunkSize = 36 + subchunk2Size

    var data = Data()
    // RIFF chunk descriptor
    data.append(contentsOf: [0x52, 0x49, 0x46, 0x46]) // "RIFF"
    data.append(contentsOf: withUnsafeBytes(of: chunkSize.littleEndian) { Array($0) })
    data.append(contentsOf: [0x57, 0x41, 0x56, 0x45]) // "WAVE"

    // fmt subchunk
    data.append(contentsOf: [0x66, 0x6d, 0x74, 0x20]) // "fmt "
    let subchunk1Size: UInt32 = 16
    data.append(contentsOf: withUnsafeBytes(of: subchunk1Size.littleEndian) { Array($0) })
    let audioFormat: UInt16 = 1 // PCM
    data.append(contentsOf: withUnsafeBytes(of: audioFormat.littleEndian) { Array($0) })
    let numChannels: UInt16 = 1 // Mono
    data.append(contentsOf: withUnsafeBytes(of: numChannels.littleEndian) { Array($0) })
    data.append(contentsOf: withUnsafeBytes(of: sampleRate.littleEndian) { Array($0) })
    let byteRate: UInt32 = sampleRate * 1 * 1
    data.append(contentsOf: withUnsafeBytes(of: byteRate.littleEndian) { Array($0) })
    let blockAlign: UInt16 = 1
    data.append(contentsOf: withUnsafeBytes(of: blockAlign.littleEndian) { Array($0) })
    let bitsPerSample: UInt16 = 8
    data.append(contentsOf: withUnsafeBytes(of: bitsPerSample.littleEndian) { Array($0) })

    // data subchunk
    data.append(contentsOf: [0x64, 0x61, 0x74, 0x61]) // "data"
    data.append(contentsOf: withUnsafeBytes(of: subchunk2Size.littleEndian) { Array($0) })
    // In 8-bit PCM, 128 (0x80) represents silence
    let silence = [UInt8](repeating: 128, count: Int(numSamples))
    data.append(contentsOf: silence)

    return data
  }
}
