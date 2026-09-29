import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

import 'package:client_mobile/core/bainiu_protocol.dart';
import 'package:client_mobile/core/crc8.dart';
import 'package:client_mobile/core/constants.dart';
import 'package:client_mobile/engine/canvas_rasterizer.dart';
import 'package:client_mobile/engine/dithering_engine.dart';
import 'package:client_mobile/engine/photo_processor.dart';
import 'package:client_mobile/engine/pdf_processor.dart';
import 'package:client_mobile/engine/qr_rasterizer.dart';

void main() {
  test('Bainiu Protocol CRC8 Calculation', () {
    final testData = [0xAA, 0x55, 0x17];
    final crc = calculateCrc8(testData);
    expect(crc, isA<int>());
    expect(crc >= 0 && crc <= 255, isTrue);
  });

  test('Bainiu makePacket Framing', () {
    final packet = makePacket(0xBD, Uint8List.fromList([0x01]));
    expect(packet.length, equals(9));
    expect(packet[0], equals(0x51));
    expect(packet[1], equals(0x78));
    expect(packet[2], equals(0xBD));
    expect(packet[packet.length - 1], equals(0xFF));
  });

  test('Dithering Engine Produces 384-dot 1-bit Image', () {
    final testImg = img.Image(width: kPrintWidth, height: 100);
    // Fill with gradient
    for (int y = 0; y < 100; y++) {
      for (int x = 0; x < kPrintWidth; x++) {
        final val = (x * 255) ~/ kPrintWidth;
        testImg.setPixelRgb(x, y, val, val, val);
      }
    }

    final floyd = floydSteinbergDither(testImg);
    expect(floyd.width, equals(kPrintWidth));
    expect(floyd.height, equals(100));

    final atkinson = atkinsonDither(testImg);
    expect(atkinson.width, equals(kPrintWidth));
    expect(atkinson.height, equals(100));

    final bayer = bayerDither(testImg);
    expect(bayer.width, equals(kPrintWidth));
    expect(bayer.height, equals(100));

    final rows = encodeImageToLsbRows(floyd);
    expect(rows.length, equals(100));
    expect(rows.first.length, equals(kPrintWidth ~/ 8)); // 48 bytes per row
  });

  test('Photo Processor Presets', () {
    expect(kPhotoPresets.containsKey('portrait'), isTrue);
    expect(kPhotoPresets.containsKey('sharp'), isTrue);
    expect(kPhotoPresets.containsKey('balanced'), isTrue);
    expect(kPhotoPresets.containsKey('high_contrast'), isTrue);
    expect(kPhotoPresets.containsKey('halftone'), isTrue);
  });

  test('Process photo via compute and runPhotoProcessingIsolate', () async {
    final testImg = img.Image(width: 500, height: 500);
    testImg.clear(img.ColorUint8.rgb(200, 200, 200));

    final result = await compute(
      runPhotoProcessingIsolate,
      PhotoProcessInput(
        image: testImg,
        preset: 'portrait',
        ditherAlgo: 'floyd',
        sharpness: 1.2,
        contrast: 1.12,
        brightness: 1.08,
        autocrop: false,
        strength: 4,
      ),
    );

    expect(result.processedImage.width, equals(kPrintWidth));
    expect(result.pngBytes.isNotEmpty, isTrue);
  });

  test('Decode photo via compute and runPhotoDecodeIsolate', () async {
    final testImg = img.Image(width: 300, height: 300);
    testImg.clear(img.ColorUint8.rgb(180, 180, 180));
    final testBytes = Uint8List.fromList(img.encodePng(testImg));

    final result = await compute(
      runPhotoDecodeIsolate,
      PhotoDecodeInput(
        bytes: testBytes,
        preset: 'portrait',
        ditherAlgo: 'floyd',
        sharpness: 1.2,
        contrast: 1.12,
        brightness: 1.08,
        autocrop: false,
        strength: 4,
      ),
    );

    expect(result, isNotNull);
    expect(result!.processedImage.width, equals(kPrintWidth));
    expect(result.pngBytes.isNotEmpty, isTrue);
  });

  test('Decode PNG and encodeImageToLsbRows', () {
    // Create an image with white background (255) and a black box (0)
    final canvas = img.Image(width: 384, height: 10, numChannels: 1);
    canvas.clear(img.ColorUint8.rgb(255, 255, 255));
    // Set first pixel to black
    canvas.setPixelRgb(0, 0, 0, 0, 0);

    final pngBytes = img.encodePng(canvas);
    final decoded = img.decodeImage(pngBytes);
    expect(decoded, isNotNull);

    final rows = encodeImageToLsbRows(decoded!);
    // First pixel is black, so bit 0 of byte 0 should be 1
    // Second pixel is white, so bit 1 of byte 0 should be 0
    expect(rows[0][0] & 1, equals(1)); // bit 0 = 1 (black)
    expect(rows[0][0] & 2, equals(0)); // bit 1 = 0 (white)
    // All other bytes in row 0 should be 0 (white)
    for (int i = 1; i < 48; i++) {
      expect(rows[0][i], equals(0));
    }
  });

  test('Compare /tmp/web_photo_test.png with Python', () {
    final file = File('/tmp/web_photo_test.png');
    final webPhotoFile = File('/tmp/test_web_photo_out.png');
    if (webPhotoFile.existsSync()) {
      final decoded = img.decodeImage(webPhotoFile.readAsBytesSync())!;
      print('test_web_photo_out.png: channels=${decoded.numChannels}, format=${decoded.format}');
      final rows = encodeImageToLsbRows(decoded, threshold: 150);
      int blackDots = 0;
      for (final row in rows) {
        for (final byte in row) {
          for (int b = 0; b < 8; b++) {
            if ((byte & (1 << b)) != 0) blackDots++;
          }
        }
        print('test_web_photo_out blackDots: $blackDots');
      }
    }
    final richFile = File('/tmp/rich_test_input.png');
    if (richFile.existsSync()) {
      final richInput = img.decodeImage(richFile.readAsBytesSync())!;
      for (final preset in ['portrait', 'sharp', 'balanced', 'high_contrast', 'halftone']) {
        final processed = processPhoto(original: richInput, preset: preset, autocrop: false, strength: 4);
        final rows = encodeImageToLsbRows(processed);
        int bDots = 0;
        for (final row in rows) {
          for (final byte in row) {
            for (int b = 0; b < 8; b++) {
              if ((byte & (1 << b)) != 0) bDots++;
            }
          }
        }
        final rTotal = rows.length * 384;
        print('Dart $preset: black=$bDots (${bDots / rTotal * 100}%)');
      }
    }
    final pil1File = File('/tmp/pil_mode_1.png');
    if (pil1File.existsSync()) {
      final p1Decoded = img.decodeImage(pil1File.readAsBytesSync())!;
      print('PIL mode 1 image: channels=${p1Decoded.numChannels}, format=${p1Decoded.format}');
      final pWhite = p1Decoded.getPixel(0, 0);
      final pBlack = p1Decoded.getPixel(10, 10);
      print('pWhite: r=${pWhite.r}, rNorm=${pWhite.rNormalized}, lumNorm=${pWhite.luminanceNormalized}');
      print('pBlack: r=${pBlack.r}, rNorm=${pBlack.rNormalized}, lumNorm=${pBlack.luminanceNormalized}');
      final p1Rows = encodeImageToLsbRows(p1Decoded);
      int p1BlackDots = 0;
      for (final row in p1Rows) {
        for (final byte in row) {
          for (int b = 0; b < 8; b++) {
            if ((byte & (1 << b)) != 0) p1BlackDots++;
          }
        }
      }
      print('PIL mode 1 encoded dots: total=${p1Rows.length * 384}, black=$p1BlackDots');
    }
    final bytes = file.readAsBytesSync();
    final decoded = img.decodeImage(bytes);
    expect(decoded, isNotNull);

    final rows = encodeImageToLsbRows(decoded!);
    int blackDots = 0;
    for (final row in rows) {
      for (final byte in row) {
        for (int b = 0; b < 8; b++) {
          if ((byte & (1 << b)) != 0) blackDots++;
        }
      }
    }
    final totalDots = rows.length * 384;
    print('Dart from Python PNG: total dots=$totalDots, black dots=$blackDots (${blackDots / totalDots * 100}%)');
    expect(blackDots, equals(2410));

    final dartInput = img.Image(width: 384, height: 50);
    dartInput.clear(img.ColorUint8.rgb(200, 200, 200));
    for (int i = 0; i < 50; i++) {
      dartInput.setPixelRgb(i, i, 0, 0, 0);
    }
    print('dartInput pixel(100,20) r=${dartInput.getPixel(100, 20).r}, lumNorm=${dartInput.getPixel(100, 20).luminanceNormalized}');

    final dartProcessed = processPhoto(original: dartInput, preset: 'portrait', sharpness: 0.0, strength: 4, autocrop: false);
    print('dartProcessed pixel(100,20) with sharpness=0: r=${dartProcessed.getPixel(100, 20).r}, lumNorm=${dartProcessed.getPixel(100, 20).luminanceNormalized}');

    final dartRows = encodeImageToLsbRows(dartProcessed);
    int dartBlackDots = 0;
    for (final row in dartRows) {
      for (final byte in row) {
        for (int b = 0; b < 8; b++) {
          if ((byte & (1 << b)) != 0) dartBlackDots++;
        }
      }
    }
    print('Dart processPhoto: total dots=$totalDots, black dots=$dartBlackDots (${dartBlackDots / totalDots * 100}%)');
  });

  testWidgets('renderTextToBitmap generates valid 384-dot monochrome bitmap', (tester) async {
    final bitmap = await tester.runAsync(() => renderTextToBitmap(
      text: 'Hello TinyPOS\nMultilingual & Thermal Test',
      options: const TextRenderOptions(fontSize: 24, isBold: false),
    ));

    expect(bitmap, isNotNull);
    expect(bitmap!.width, equals(384));
    expect(bitmap.height, greaterThan(0));

    // Verify PNG encoding works for preview
    final png = img.encodePng(bitmap);
    expect(png.isNotEmpty, isTrue);

    // Verify LSB rows encoding works
    final rows = encodeImageToLsbRows(bitmap);
    expect(rows.length, equals(bitmap.height));
    expect(rows.first.length, equals(48));
  });

  testWidgets('renderQrToBitmap generates valid 384-dot monochrome bitmap', (tester) async {
    final bitmap = await tester.runAsync(() => renderQrToBitmap(
      const QrPrintPayload(
        qrContent: 'https://pos.sayem.top',
        headerText: 'Scan to Connect',
        footerText: 'TinyPOS Terminal',
      ),
    ));

    expect(bitmap, isNotNull);
    expect(bitmap!.width, equals(384));
    expect(bitmap.height, greaterThan(0));

    final png = img.encodePng(bitmap);
    expect(png.isNotEmpty, isTrue);

    final rows = encodeImageToLsbRows(bitmap);
    expect(rows.length, equals(bitmap.height));
    expect(rows.first.length, equals(48));
  });

  test('flattenAlphaOnWhite transforms transparent pixels to pure white', () {
    // 4-channel image where all pixels are fully transparent (alpha=0, rgb=0)
    final transparentImg = img.Image(width: 50, height: 50, numChannels: 4);
    for (int y = 0; y < 50; y++) {
      for (int x = 0; x < 50; x++) {
        transparentImg.setPixelRgba(x, y, 0, 0, 0, 0);
      }
    }
    // Put a small black square in the center (alpha=255, rgb=0)
    for (int y = 20; y < 30; y++) {
      for (int x = 20; x < 30; x++) {
        transparentImg.setPixelRgba(x, y, 0, 0, 0, 255);
      }
    }

    final flattened = flattenAlphaOnWhite(transparentImg);
    expect(flattened.numChannels, equals(3));
    // Transparent area MUST be pure white (255, 255, 255), NEVER black!
    final cornerPixel = flattened.getPixel(0, 0);
    expect(cornerPixel.r, equals(255));
    expect(cornerPixel.g, equals(255));
    expect(cornerPixel.b, equals(255));

    // Center square must stay black (0, 0, 0)
    final centerPixel = flattened.getPixel(25, 25);
    expect(centerPixel.r, equals(0));
    expect(centerPixel.g, equals(0));
    expect(centerPixel.b, equals(0));
  });

  test('processDocumentImage produces crisp 384-dot bitmap on white background', () {
    // Simulate a transparent PDF page with black text
    final docImg = img.Image(width: 600, height: 800, numChannels: 4);
    for (int y = 0; y < 800; y++) {
      for (int x = 0; x < 600; x++) {
        docImg.setPixelRgba(x, y, 0, 0, 0, 0); // transparent background
      }
    }
    // Add black header text bar
    for (int y = 100; y < 140; y++) {
      for (int x = 50; x < 550; x++) {
        docImg.setPixelRgba(x, y, 0, 0, 0, 255);
      }
    }

    final processed = processDocumentImage(docImg, autocrop: false);
    expect(processed.width, equals(kPrintWidth)); // 384 dots

    // Background pixel must be white (255)
    final bgPixel = processed.getPixel(10, 10);
    expect(bgPixel.r, equals(255));

    // Text bar pixel must be black (0) at y=75 (scaled from y=120)
    final textPixel = processed.getPixel(192, 75);
    expect(textPixel.r, equals(0));

    // Ensure LSB row encoding contains mostly white rows and black text rows
    final rows = encodeImageToLsbRows(processed);
    expect(rows.length, equals(processed.height));
    expect(rows.first.every((b) => b == 0), isTrue); // Top row is all white (0x00)
  });
}

