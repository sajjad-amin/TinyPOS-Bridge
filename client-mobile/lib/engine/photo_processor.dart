/// Dedicated Photo Studio image processor matching TinyPOS server presets and dithering.
library;

import 'dart:typed_data';
import 'package:image/image.dart' as img;
import '../core/constants.dart';
import 'dithering_engine.dart';

class PhotoPreset {
  final String key;
  final String title;
  final String description;
  final String dither;
  final double sharpness;
  final double contrast;
  final double brightness;

  const PhotoPreset({
    required this.key,
    required this.title,
    required this.description,
    required this.dither,
    required this.sharpness,
    required this.contrast,
    required this.brightness,
  });
}

const Map<String, PhotoPreset> kPhotoPresets = {
  'portrait': PhotoPreset(
    key: 'portrait',
    title: 'Portrait / Face',
    description: 'Lifted shadows to avoid blotchy skin tones',
    dither: 'floyd',
    sharpness: 1.2,
    contrast: 1.12,
    brightness: 1.08,
  ),
  'sharp': PhotoPreset(
    key: 'sharp',
    title: 'Crisp & Detailed',
    description: 'High-definition edge enhancement for eyes, hair, jewelry',
    dither: 'atkinson',
    sharpness: 2.0,
    contrast: 1.22,
    brightness: 1.05,
  ),
  'balanced': PhotoPreset(
    key: 'balanced',
    title: 'Balanced / Landscape',
    description: 'Natural dynamic range for everyday photos and outdoor scenes',
    dither: 'floyd',
    sharpness: 1.0,
    contrast: 1.15,
    brightness: 1.03,
  ),
  'high_contrast': PhotoPreset(
    key: 'high_contrast',
    title: 'High Contrast',
    description: 'Punchy deep blacks and bright whites for logos and ink art',
    dither: 'atkinson',
    sharpness: 1.5,
    contrast: 1.38,
    brightness: 1.00,
  ),
  'halftone': PhotoPreset(
    key: 'halftone',
    title: 'Retro Halftone',
    description: 'Vintage newsprint & comic book 8x8 dot matrix pattern',
    dither: 'bayer',
    sharpness: 1.0,
    contrast: 1.20,
    brightness: 1.02,
  ),
};

/// Automatically crops uniform white margins/borders.
img.Image autocropWhitespace(img.Image input, {int threshold = 240, int padding = 4}) {
  final int w = input.width;
  final int h = input.height;

  int minX = w;
  int minY = h;
  int maxX = 0;
  int maxY = 0;
  bool foundNonWhite = false;

  // Stride optimization for high-resolution images
  final int step = (w > 1000 || h > 1000) ? 4 : 1;

  for (int y = 0; y < h; y += step) {
    for (int x = 0; x < w; x += step) {
      final p = input.getPixel(x, y);
      if (input.hasAlpha && p.aNormalized < 0.5) continue;
      final lum = p.luminanceNormalized * 255.0;
      if (lum < threshold) {
        foundNonWhite = true;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }

  if (!foundNonWhite || minX > maxX || minY > maxY) {
    return input;
  }

  // Add breathing margin
  minX = (minX - padding).clamp(0, w - 1);
  minY = (minY - padding).clamp(0, h - 1);
  maxX = (maxX + padding).clamp(0, w - 1);
  maxY = (maxY + padding).clamp(0, h - 1);

  final cropW = maxX - minX + 1;
  final cropH = maxY - minY + 1;

  if (cropW < 20 || cropH < 20) return input;
  return img.copyCrop(input, x: minX, y: minY, width: cropW, height: cropH);
}

/// Flattens transparency against a solid pure white background.
/// Uses mathematical linear alpha compositing onto RGB (255, 255, 255):
/// out = pixel * alpha + 255 * (1 - alpha).
/// Ensures transparent PDF/PNG page backgrounds never turn pitch black.
img.Image flattenAlphaOnWhite(img.Image input) {
  if (!input.hasAlpha) return input;
  final int w = input.width;
  final int h = input.height;
  final out = img.Image(width: w, height: h, numChannels: 3);

  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      final p = input.getPixel(x, y);
      final double a = p.aNormalized.toDouble();
      if (a >= 0.999) {
        out.setPixelRgb(x, y, p.r, p.g, p.b);
      } else if (a <= 0.001) {
        out.setPixelRgb(x, y, 255, 255, 255);
      } else {
        final double invA = 1.0 - a;
        final int r = (p.r * a + 255.0 * invA).round().clamp(0, 255);
        final int g = (p.g * a + 255.0 * invA).round().clamp(0, 255);
        final int b = (p.b * a + 255.0 * invA).round().clamp(0, 255);
        out.setPixelRgb(x, y, r, g, b);
      }
    }
  }
  return out;
}

/// Spatial unsharp mask sharpening on grayscale buffer.
/// Uses a noise threshold of 2.0 to avoid exaggerating camera sensor grain on flat surfaces/faces.
void applyGrayscaleUnsharpMask({
  required Uint8List buffer,
  required int width,
  required int height,
  required double amount,
  double threshold = 2.0,
}) {
  if (amount <= 0.05) return;

  // Build RGB image for clean Gaussian blur without channel ambiguity
  final tempImg = img.Image(width: width, height: height);
  for (int y = 0; y < height; y++) {
    final int yOffset = y * width;
    for (int x = 0; x < width; x++) {
      final int v = buffer[yOffset + x];
      tempImg.setPixelRgb(x, y, v, v, v);
    }
  }

  final blurred = img.gaussianBlur(tempImg, radius: amount > 1.5 ? 2 : 1);

  for (int y = 0; y < height; y++) {
    final int yOffset = y * width;
    for (int x = 0; x < width; x++) {
      final int idx = yOffset + x;
      final int orig = buffer[idx];
      final int blur = blurred.getPixel(x, y).r.toInt();
      final int diff = orig - blur;

      if (diff.abs() >= threshold) {
        final double sharpened = orig + diff * amount;
        buffer[idx] = sharpened.round().clamp(0, 255);
      }
    }
  }
}

/// Full photo rendering pipeline matching the Python server engine.
/// Produces a 384-dot wide 1-bit dithered image optimized for 200dpi thermal receipt paper.
img.Image processPhoto({
  required img.Image original,
  String preset = 'portrait',
  String? ditherAlgo,
  double? sharpness,
  double? contrast,
  double? brightness,
  bool autocrop = true,
  int strength = 4,
}) {
  final config = kPhotoPresets[preset] ?? kPhotoPresets['portrait']!;

  final activeDither = ditherAlgo ?? config.dither;
  final activeSharpness = sharpness ?? config.sharpness;
  final activeContrast = contrast ?? config.contrast;
  final activeBrightness = brightness ?? config.brightness;

  // 1. Flatten alpha/transparency against pure white background
  img.Image work = flattenAlphaOnWhite(original);

  // 2. Autocrop margins if requested
  if (autocrop) {
    work = autocropWhitespace(work);
  }

  // 3. High quality downsampling to 384 dots width
  final double aspectRatio = work.height / work.width;
  final int targetHeight = (kPrintWidth * aspectRatio).round().clamp(1, 15000);
  work = img.copyResize(
    work,
    width: kPrintWidth,
    height: targetHeight,
    interpolation: img.Interpolation.average, // Box area average for anti-aliased downsampling
  );

  final int w = work.width;
  final int h = work.height;
  final int totalPixels = w * h;

  // 4. Exact ITU-R 601-2 grayscale conversion matching Pillow Image.convert('L')
  final Uint8List grayBuffer = imageToGrayscaleBytes(work);

  // 5. Edge sharpening on grayscale (Unsharp mask with noise threshold)
  if (activeSharpness > 0.05) {
    applyGrayscaleUnsharpMask(
      buffer: grayBuffer,
      width: w,
      height: h,
      amount: activeSharpness,
      threshold: 2.0,
    );
  }

  // 6. Contrast & Brightness calibration matching Python PIL ImageEnhance:
  // Contrast interpolates around integer mean luminance: cMean + (val - cMean) * factor
  // Brightness scales linearly: val * factor
  int sumLum = 0;
  for (int i = 0; i < totalPixels; i++) {
    sumLum += grayBuffer[i];
  }
  final double meanLum = totalPixels > 0 ? (sumLum / totalPixels) : 128.0;
  final int cMean = (meanLum + 0.5).toInt();

  final double strengthBoost = strength < 5 ? (1.0 + (5 - strength) * 0.03) : 1.0;

  for (int i = 0; i < totalPixels; i++) {
    double val = grayBuffer[i].toDouble();

    // Contrast towards image mean (Pillow ImageEnhance.Contrast)
    if ((activeContrast - 1.0).abs() > 0.001) {
      val = cMean + (val - cMean) * activeContrast;
    }

    // Brightness adjustment (Pillow ImageEnhance.Brightness)
    if ((activeBrightness - 1.0).abs() > 0.001) {
      val = val * activeBrightness;
    }

    // Strength tuning shadow lift to prevent thermal pin dot-pooling
    if (strengthBoost > 1.0) {
      val = val * strengthBoost;
    }

    grayBuffer[i] = val.round().clamp(0, 255);
  }

  // 7. Apply selected dithering algorithm directly from grayBuffer
  switch (activeDither.toLowerCase()) {
    case 'atkinson':
      return atkinsonDitherBytes(grayBuffer, w, h);
    case 'bayer':
    case 'halftone':
    case 'ordered':
      return bayerDitherBytes(grayBuffer, w, h);
    case 'floyd':
    default:
      return floydSteinbergDitherBytes(grayBuffer, w, h);
  }
}

/// Parameters for background photo processing
class PhotoProcessInput {
  final img.Image image;
  final String preset;
  final String ditherAlgo;
  final double sharpness;
  final double contrast;
  final double brightness;
  final bool autocrop;
  final int strength;

  const PhotoProcessInput({
    required this.image,
    required this.preset,
    required this.ditherAlgo,
    required this.sharpness,
    required this.contrast,
    required this.brightness,
    required this.autocrop,
    required this.strength,
  });
}

class PhotoProcessOutput {
  final img.Image processedImage;
  final Uint8List pngBytes;

  const PhotoProcessOutput({
    required this.processedImage,
    required this.pngBytes,
  });
}

/// Parameters for background photo decoding and processing
class PhotoDecodeInput {
  final Uint8List bytes;
  final String preset;
  final String ditherAlgo;
  final double sharpness;
  final double contrast;
  final double brightness;
  final bool autocrop;
  final int strength;

  const PhotoDecodeInput({
    required this.bytes,
    required this.preset,
    required this.ditherAlgo,
    required this.sharpness,
    required this.contrast,
    required this.brightness,
    required this.autocrop,
    required this.strength,
  });
}

class PhotoDecodeOutput {
  final img.Image rawImage;
  final img.Image processedImage;
  final Uint8List pngBytes;

  const PhotoDecodeOutput({
    required this.rawImage,
    required this.processedImage,
    required this.pngBytes,
  });
}

/// Pure top-level isolate worker for photo processing.
/// Cannot capture Flutter State, Element, or WidgetsFlutterBinding.
PhotoProcessOutput runPhotoProcessingIsolate(PhotoProcessInput input) {
  final processed = processPhoto(
    original: input.image,
    preset: input.preset,
    ditherAlgo: input.ditherAlgo,
    sharpness: input.sharpness,
    contrast: input.contrast,
    brightness: input.brightness,
    autocrop: input.autocrop,
    strength: input.strength,
  );

  final pngBytes = Uint8List.fromList(img.encodePng(processed));
  return PhotoProcessOutput(
    processedImage: processed,
    pngBytes: pngBytes,
  );
}

/// Pure top-level isolate worker for decoding and initial processing.
/// Cannot capture Flutter State, Element, or WidgetsFlutterBinding.
PhotoDecodeOutput? runPhotoDecodeIsolate(PhotoDecodeInput input) {
  img.Image? decoded = img.decodeImage(input.bytes);
  if (decoded == null) return null;

  // Downscale large camera captures (e.g. 48MP iPhone 15 Pro Max) to max dimension 1200
  final int maxDim = decoded.width > decoded.height ? decoded.width : decoded.height;
  if (maxDim > 1200) {
    final double scale = 1200.0 / maxDim;
    final int targetW = (decoded.width * scale).round();
    final int targetH = (decoded.height * scale).round();
    decoded = img.copyResize(
      decoded,
      width: targetW,
      height: targetH,
      interpolation: img.Interpolation.average,
    );
  }

  final processed = processPhoto(
    original: decoded,
    preset: input.preset,
    ditherAlgo: input.ditherAlgo,
    sharpness: input.sharpness,
    contrast: input.contrast,
    brightness: input.brightness,
    autocrop: input.autocrop,
    strength: input.strength,
  );

  final pngBytes = Uint8List.fromList(img.encodePng(processed));
  return PhotoDecodeOutput(
    rawImage: decoded,
    processedImage: processed,
    pngBytes: pngBytes,
  );
}
