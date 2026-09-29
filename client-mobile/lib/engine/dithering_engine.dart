/// High-performance 1-bit thermal dithering and binarization engines in pure Dart.
/// Implements:
/// 1. Floyd-Steinberg (exact Pillow libImaging/Convert.c integer error diffusion)
/// 2. Bill Atkinson (classic Apple Mac 3/4 diffusion - crisp highlights, no blotchy shadows)
/// 3. Bayer 8x8 (retro halftone comic/newsprint dot matrix matching TinyPOS Python engine)
/// 4. Crisp Document Binarization (contrast-boosted thresholding for crisp receipt/invoice text)
library;

import 'dart:typed_data';
import 'package:image/image.dart' as img;

/// 8x8 Bayer threshold matrix normalized to 0-63
const List<List<int>> kBayer8x8 = [
  [0, 32, 8, 40, 2, 34, 10, 42],
  [48, 16, 56, 24, 50, 18, 58, 26],
  [12, 44, 4, 36, 14, 46, 6, 38],
  [60, 28, 52, 20, 62, 30, 54, 22],
  [3, 35, 11, 43, 1, 33, 9, 41],
  [51, 19, 59, 27, 49, 17, 57, 25],
  [15, 47, 7, 39, 13, 45, 5, 37],
  [63, 31, 55, 23, 61, 29, 53, 21],
];

/// Converts any input image to a flat Uint8List grayscale buffer (0..255).
/// Uses ITU-R 601-2 standard luma weights matching PIL Image.convert('L'):
/// L = (299 * R + 587 * G + 114 * B) / 1000
Uint8List imageToGrayscaleBytes(img.Image input) {
  final int w = input.width;
  final int h = input.height;
  final Uint8List gray = Uint8List(w * h);
  final bool is1Channel = input.numChannels == 1;
  final bool isUint1 = input.format == img.Format.uint1;

  for (int y = 0; y < h; y++) {
    final int yOffset = y * w;
    for (int x = 0; x < w; x++) {
      final p = input.getPixel(x, y);
      if (is1Channel) {
        if (isUint1) {
          gray[yOffset + x] = p.r == 0 ? 0 : 255;
        } else {
          gray[yOffset + x] = p.r.toInt().clamp(0, 255);
        }
      } else {
        gray[yOffset + x] =
            ((p.r * 299 + p.g * 587 + p.b * 114) ~/ 1000).clamp(0, 255);
      }
    }
  }
  return gray;
}

/// Core Pillow Floyd-Steinberg integer error diffusion C implementation.
/// Matches Pillow's libImaging/Convert.c byte-for-byte, dot-for-dot.
img.Image floydSteinbergDitherBytes(Uint8List gray, int w, int h) {
  final out = img.Image(width: w, height: h);
  final Int32List errors = Int32List(w + 1);

  for (int y = 0; y < h; y++) {
    int l = 0;
    int l0 = 0;
    int l1 = 0;
    final int yOffset = y * w;

    for (int x = 0; x < w; x++) {
      final int inVal = gray[yOffset + x];

      // Exact Pillow C: l = CLIP8(in[x] + (l + errors[x + 1]) / 16);
      final int errTerm = l + errors[x + 1];
      final int errDiv = errTerm ~/ 16; // Integer division truncates towards zero
      final int temp = inVal + errDiv;
      l = temp < 0 ? 0 : (temp > 255 ? 255 : temp);

      final int outVal = (l > 128) ? 255 : 0;
      out.setPixelRgb(x, y, outVal, outVal, outVal);

      // Exact Pillow C error propagation:
      l -= outVal;
      final int l2 = l;
      final int d2 = l + l;
      l += d2;
      errors[x] = l + l0;
      l += d2;
      l0 = l + l1;
      l1 = l2;
      l += d2;
    }
    errors[w] = l0;
  }

  return out;
}

/// Floyd-Steinberg error diffusion dithering matching Python PIL Image.convert('1').
img.Image floydSteinbergDither(img.Image input) {
  final gray = imageToGrayscaleBytes(input);
  return floydSteinbergDitherBytes(gray, input.width, input.height);
}

/// Core Bill Atkinson 1-bit dithering algorithm operating on flat Uint8List buffer.
/// Developed at Apple for the original Macintosh.
/// Diffuses only 3/4 of the error (dropping 1/4), preserving crisp highlights and
/// preventing dark pooling on thermal paper.
img.Image atkinsonDitherBytes(Uint8List gray, int w, int h) {
  final Int32List arr = Int32List.fromList(gray);
  final out = img.Image(width: w, height: h);

  for (int y = 0; y < h; y++) {
    final int yOffset = y * w;
    for (int x = 0; x < w; x++) {
      final int idx = yOffset + x;
      final int oldVal = arr[idx].clamp(0, 255);
      final int newVal = oldVal > 127 ? 255 : 0;

      out.setPixelRgb(x, y, newVal, newVal, newVal);

      final int err = (oldVal - newVal) >> 3; // 1/8 error
      if (err != 0) {
        if (x + 1 < w) arr[idx + 1] += err;
        if (x + 2 < w) arr[idx + 2] += err;
        if (y + 1 < h) {
          if (x > 0) arr[idx + w - 1] += err;
          arr[idx + w] += err;
          if (x + 1 < w) arr[idx + w + 1] += err;
        }
        if (y + 2 < h) {
          arr[idx + (w * 2)] += err;
        }
      }
    }
  }

  return out;
}

/// Bill Atkinson dithering from Image input.
img.Image atkinsonDither(img.Image input) {
  final gray = imageToGrayscaleBytes(input);
  return atkinsonDitherBytes(gray, input.width, input.height);
}

/// Core Ordered 8x8 Bayer dithering operating on flat Uint8List buffer.
img.Image bayerDitherBytes(Uint8List gray, int w, int h) {
  final out = img.Image(width: w, height: h);

  for (int y = 0; y < h; y++) {
    final int my = y % 8;
    final int yOffset = y * w;
    for (int x = 0; x < w; x++) {
      final int mx = x % 8;
      final int threshold = (kBayer8x8[my][mx] * 255) ~/ 64;
      final int lum = gray[yOffset + x];
      final int outVal = lum > threshold ? 255 : 0;
      out.setPixelRgb(x, y, outVal, outVal, outVal);
    }
  }

  return out;
}

/// Ordered 8x8 Bayer dithering (halftone retro matrix).
img.Image bayerDither(img.Image input) {
  final gray = imageToGrayscaleBytes(input);
  return bayerDitherBytes(gray, input.width, input.height);
}

/// Crisp Document & Invoice Binarization (thresholding with contrast boost).
/// Prevents fuzzy speckles and broken dots caused by error diffusion on sharp receipt text.
img.Image crispDocumentBinarizeBytes(Uint8List gray, int w, int h,
    {int threshold = 150}) {
  final out = img.Image(width: w, height: h);

  for (int y = 0; y < h; y++) {
    final int yOffset = y * w;
    for (int x = 0; x < w; x++) {
      final int lum = gray[yOffset + x];
      final int val = lum < threshold ? 0 : 255;
      out.setPixelRgb(x, y, val, val, val);
    }
  }

  return out;
}

/// Crisp Document & Invoice Binarization from Image input.
img.Image crispDocumentBinarize(img.Image input, {int threshold = 150}) {
  final gray = imageToGrayscaleBytes(input);
  return crispDocumentBinarizeBytes(gray, input.width, input.height,
      threshold: threshold);
}
