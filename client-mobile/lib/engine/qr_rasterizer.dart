/// Thermal QR code generator and rasterizer with optional header and footer text.
library;

import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import 'package:qr_flutter/qr_flutter.dart';

import '../core/constants.dart';
import 'dithering_engine.dart';

class QrPrintPayload {
  final String qrContent;
  final String? headerText;
  final String? footerText;
  final double qrSize; // e.g. 260-320px

  const QrPrintPayload({
    required this.qrContent,
    this.headerText,
    this.footerText,
    this.qrSize = 280.0,
  });

  /// Format Wi-Fi credentials into standard Wi-Fi barcode syntax:
  /// WIFI:T:WPA;S:MyNetwork;P:MyPassword;;
  static String formatWifi({
    required String ssid,
    required String password,
    String authType = 'WPA',
    bool isHidden = false,
  }) {
    final enc = authType.toUpperCase() == 'NONE' ? 'nopass' : authType.toUpperCase();
    final hiddenPart = isHidden ? 'H:true;' : '';
    final passPart = enc == 'nopass' ? '' : 'P:$password;';
    return 'WIFI:T:$enc;S:$ssid;$passPart$hiddenPart;';
  }
}

/// Renders a thermal-optimized QR code with optional header and footer onto a 384px canvas.
Future<img.Image> renderQrToBitmap(QrPrintPayload payload) async {
  final double canvasWidth = kPrintWidth.toDouble();

  // 1. Prepare Header text painter if present
  TextPainter? headerPainter;
  if (payload.headerText != null && payload.headerText!.trim().isNotEmpty) {
    headerPainter = TextPainter(
      text: TextSpan(
        text: payload.headerText!.trim(),
        style: const TextStyle(
          color: Colors.black,
          fontSize: 22.0,
          fontWeight: FontWeight.bold,
          height: 1.2,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
    );
    headerPainter.layout(minWidth: canvasWidth - 16, maxWidth: canvasWidth - 16);
  }

  // 2. Prepare Footer text painter if present
  TextPainter? footerPainter;
  if (payload.footerText != null && payload.footerText!.trim().isNotEmpty) {
    footerPainter = TextPainter(
      text: TextSpan(
        text: payload.footerText!.trim(),
        style: const TextStyle(
          color: Colors.black,
          fontSize: 18.0,
          height: 1.2,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
    );
    footerPainter.layout(minWidth: canvasWidth - 16, maxWidth: canvasWidth - 16);
  }

  // 3. Compute total height
  const double topMargin = 16.0;
  const double bottomMargin = 16.0;
  const double itemSpacing = 12.0;

  double totalHeight = topMargin + payload.qrSize + bottomMargin;
  if (headerPainter != null) {
    totalHeight += headerPainter.height + itemSpacing;
  }
  if (footerPainter != null) {
    totalHeight += footerPainter.height + itemSpacing;
  }

  // 4. Create Canvas
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);

  // Background white
  final bgPaint = Paint()..color = Colors.white;
  canvas.drawRect(Rect.fromLTWH(0, 0, canvasWidth, totalHeight), bgPaint);

  double currentY = topMargin;

  // Paint header
  if (headerPainter != null) {
    final x = (canvasWidth - headerPainter.width) / 2.0;
    headerPainter.paint(canvas, Offset(x, currentY));
    currentY += headerPainter.height + itemSpacing;
  }

  // Paint QR Code centered
  final qrPainter = QrPainter(
    data: payload.qrContent,
    version: QrVersions.auto,
    errorCorrectionLevel: QrErrorCorrectLevel.M,
    eyeStyle: const QrEyeStyle(
      eyeShape: QrEyeShape.square,
      color: Colors.black,
    ),
    dataModuleStyle: const QrDataModuleStyle(
      dataModuleShape: QrDataModuleShape.square,
      color: Colors.black,
    ),
  );

  final qrLeft = (canvasWidth - payload.qrSize) / 2.0;
  canvas.save();
  canvas.translate(qrLeft, currentY);
  qrPainter.paint(canvas, Size(payload.qrSize, payload.qrSize));
  canvas.restore();

  currentY += payload.qrSize + itemSpacing;

  // Paint footer
  if (footerPainter != null) {
    final x = (canvasWidth - footerPainter.width) / 2.0;
    footerPainter.paint(canvas, Offset(x, currentY));
  }

  // 5. Finalize bitmap
  final picture = recorder.endRecording();
  final ui.Image renderedImage = await picture.toImage(
    canvasWidth.toInt(),
    totalHeight.ceil(),
  );

  final byteData =
      await renderedImage.toByteData(format: ui.ImageByteFormat.rawRgba);

  if (byteData == null) {
    throw Exception('Failed to get byte data for QR canvas');
  }

  final img.Image output = img.Image.fromBytes(
    width: canvasWidth.toInt(),
    height: totalHeight.ceil(),
    bytes: byteData.buffer,
    order: img.ChannelOrder.rgba,
  );

  // Crisp binarization ensures perfect square modules without dithering noise
  return crispDocumentBinarize(output, threshold: 160);
}
