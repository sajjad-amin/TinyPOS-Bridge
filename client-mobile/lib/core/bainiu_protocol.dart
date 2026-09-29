/// Bainiu BLE thermal printer protocol packet builder, CRC8 checksum, and raster encoding.
library;

import 'dart:typed_data';
import 'package:image/image.dart' as img;

import 'constants.dart';
import 'crc8.dart';

class StrengthParams {
  final int energy;
  final Duration rowDelay;
  final int threshold;

  const StrengthParams({
    required this.energy,
    required this.rowDelay,
    required this.threshold,
  });
}

/// Create a Bainiu 0x51 0x78 protocol packet:
/// [0x51, 0x78, CMD, 0x00, LEN_L, LEN_H, DATA..., CRC8, 0xFF]
Uint8List makePacket(int cmd, [Uint8List? payload]) {
  final data = payload ?? Uint8List(0);
  final length = data.length;
  final builder = BytesBuilder(copy: false);

  builder.add(kHeader); // 0x51, 0x78
  builder.addByte(cmd & 0xFF);
  builder.addByte(0x00);
  builder.addByte(length & 0xFF);
  builder.addByte((length >> 8) & 0xFF);
  builder.add(data);

  final chk = calculateCrc8(data);
  builder.addByte(chk);
  builder.addByte(kFooter); // 0xFF

  return builder.toBytes();
}

/// Speed packet (speed 1 for dark, saturated thermal burn)
final Uint8List kCmdSetSpeed = makePacket(0xBD, Uint8List.fromList([0x01]));

/// Device status query
final Uint8List kCmdGetDevState = Uint8List.fromList([
  0x51, 0x78, 0xA3, 0x00, 0x01, 0x00, 0x00, 0x00, 0xFF,
]);

/// 200 DPI Quality packet
final Uint8List kCmdSetQuality200Dpi = Uint8List.fromList([
  0x51, 0x78, 0xA4, 0x00, 0x01, 0x00, 0x32, 0x9E, 0xFF,
]);

/// Apply energy mode packet
final Uint8List kCmdApplyEnergy = Uint8List.fromList([
  0x51, 0x78, 0xBE, 0x00, 0x01, 0x00, 0x01, 0x07, 0xFF,
]);

/// Lattice print start frame
final Uint8List kCmdLatticeStart = Uint8List.fromList([
  0x51, 0x78, 0xA6, 0x00, 0x0B, 0x00, 0xAA, 0x55, 0x17, 0x38, 0x44, 0x5F,
  0x5F, 0x5F, 0x44, 0x38, 0x2C, 0xA1, 0xFF,
]);

/// Lattice print end frame
final Uint8List kCmdLatticeEnd = Uint8List.fromList([
  0x51, 0x78, 0xA6, 0x00, 0x0B, 0x00, 0xAA, 0x55, 0x17, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x17, 0x11, 0xFF,
]);

/// Feed paper roll command (standard 96 dots feed)
final Uint8List kCmdFeedPaper = Uint8List.fromList([
  0x51, 0x78, 0xA1, 0x00, 0x02, 0x00, 0x60, 0x00, 0xF5, 0xFF,
]);

/// Construct energy packet for burn pulse length (16-bit little-endian)
Uint8List makeEnergyPacket(int energy) {
  final payload = Uint8List(2);
  final byteData = ByteData.sublistView(payload);
  byteData.setUint16(0, energy, Endian.little);
  return makePacket(0xAF, payload);
}

/// Map strength (1 to 7) to energy, row delay pacing, and threshold.
StrengthParams getStrengthParams(int strength) {
  final clamped = strength.clamp(1, 7);
  switch (clamped) {
    case 1:
      return const StrengthParams(
        energy: 8000,
        rowDelay: Duration(milliseconds: 10),
        threshold: 128,
      );
    case 2:
      return const StrengthParams(
        energy: 11000,
        rowDelay: Duration(milliseconds: 12),
        threshold: 135,
      );
    case 3:
      return const StrengthParams(
        energy: 14500,
        rowDelay: Duration(milliseconds: 14),
        threshold: 142,
      );
    case 4:
      return const StrengthParams(
        energy: 18500,
        rowDelay: Duration(milliseconds: 16),
        threshold: 150,
      );
    case 5:
      return const StrengthParams(
        energy: 22500,
        rowDelay: Duration(milliseconds: 19),
        threshold: 162,
      );
    case 6:
      return const StrengthParams(
        energy: 26500,
        rowDelay: Duration(milliseconds: 22),
        threshold: 174,
      );
    case 7:
    default:
      return const StrengthParams(
        energy: 30000,
        rowDelay: Duration(milliseconds: 26),
        threshold: 185,
      );
  }
}

/// Encode an image into Bainiu LSB-first row packets:
/// 1 dot = 1 bit (1 = black/burned pin, 0 = white/blank).
/// Each row is exactly 48 bytes (384 dots).
List<Uint8List> encodeImageToLsbRows(img.Image inputImage, {int threshold = 150}) {
  // Ensure image width is exactly 384 dots
  img.Image image = inputImage;
  if (image.width != kPrintWidth) {
    final newH = (image.height * (kPrintWidth / image.width)).round().clamp(1, 100000);
    image = img.copyResize(image, width: kPrintWidth, height: newH, interpolation: img.Interpolation.average);
  }

  final int w = image.width;
  final int h = image.height;
  final int rowByteLength = kPrintWidth ~/ 8; // 48 bytes
  final List<Uint8List> rows = [];
  final int numChannels = image.numChannels;
  final bool hasAlpha = image.hasAlpha;

  final double normThreshold = threshold / 255.0;

  for (int y = 0; y < h; y++) {
    final row = Uint8List(rowByteLength);
    for (int x = 0; x < w && x < kPrintWidth; x++) {
      final pixel = image.getPixel(x, y);

      // Transparent pixels are white paper (do not burn thermal pin)
      if (hasAlpha && pixel.aNormalized < 0.5) {
        continue;
      }

      // Compute normalized brightness (0.0 = black, 1.0 = white)
      // Uses normalized values so 1-bit (PIL mode '1'), 8-bit, and multi-channel
      // images are all evaluated correctly without treating 1-bit white (value=1) as black.
      final double brightness;
      if (numChannels == 1) {
        brightness = pixel.rNormalized.toDouble();
      } else {
        brightness = (0.299 * pixel.rNormalized +
                0.587 * pixel.gNormalized +
                0.114 * pixel.bNormalized)
            .toDouble();
      }

      final isBlack = brightness < normThreshold;

      if (isBlack) {
        final byteIdx = x >> 3; // x ~/ 8
        final bitIdx = x & 7;   // x % 8
        row[byteIdx] |= (1 << bitIdx); // LSB first
      }
    }
    rows.add(row);
  }

  return rows;
}
