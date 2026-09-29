/// High-fidelity multilingual text rasterizer using Flutter's native Canvas.
/// Renders complex typography, all world scripts (Bengali, Arabic RTL, Hindi, Chinese, etc.)
/// and full emojis to a 384-dot wide 1-bit monochrome thermal image.
library;

import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;

import '../core/constants.dart';
import 'dithering_engine.dart';

class TextRenderOptions {
  final double fontSize;
  final TextAlign textAlign;
  final bool isBold;
  final double lineSpacing;
  final int topPadding;
  final int bottomPadding;

  const TextRenderOptions({
    this.fontSize = 24.0,
    this.textAlign = TextAlign.left,
    this.isBold = false,
    this.lineSpacing = 1.25,
    this.topPadding = 12,
    this.bottomPadding = 12,
  });
}

/// Renders arbitrary text to an image.Image of exactly 384 dots width.
Future<img.Image> renderTextToBitmap({
  required String text,
  TextRenderOptions options = const TextRenderOptions(),
}) async {
  final double canvasWidth = kPrintWidth.toDouble();

  final textStyle = TextStyle(
    color: Colors.black,
    fontSize: options.fontSize,
    fontWeight: options.isBold ? FontWeight.bold : FontWeight.normal,
    height: options.lineSpacing,
    fontFamilyFallback: const [
      'sans-serif',
      'Apple Color Emoji',
      'Segoe UI Emoji',
      'Noto Color Emoji',
    ],
  );

  final textSpan = TextSpan(text: text, style: textStyle);
  final textPainter = TextPainter(
    text: textSpan,
    textAlign: options.textAlign,
    textDirection: TextDirection.ltr,
  );

  // Layout with 384px minus 8px side margins for paper edge safety
  const double sideMargin = 6.0;
  final double usableWidth = canvasWidth - (sideMargin * 2);
  textPainter.layout(minWidth: usableWidth, maxWidth: usableWidth);

  final double totalHeight =
      textPainter.height + options.topPadding + options.bottomPadding;

  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);

  // Fill solid white background
  final bgPaint = Paint()..color = Colors.white;
  canvas.drawRect(Rect.fromLTWH(0, 0, canvasWidth, totalHeight), bgPaint);

  // Paint text
  textPainter.paint(
    canvas,
    Offset(sideMargin, options.topPadding.toDouble()),
  );

  final picture = recorder.endRecording();
  final ui.Image renderedImage = await picture.toImage(
    canvasWidth.toInt(),
    totalHeight.ceil(),
  );

  final byteData =
      await renderedImage.toByteData(format: ui.ImageByteFormat.rawRgba);

  if (byteData == null) {
    throw Exception('Failed to obtain byte data from rendered text canvas');
  }

  // Convert raw RGBA to image.Image
  final img.Image output = img.Image.fromBytes(
    width: canvasWidth.toInt(),
    height: totalHeight.ceil(),
    bytes: byteData.buffer,
    order: img.ChannelOrder.rgba,
  );

  // Apply crisp thresholding to ensure crisp solid black/white text
  return crispDocumentBinarize(output, threshold: 160);
}
