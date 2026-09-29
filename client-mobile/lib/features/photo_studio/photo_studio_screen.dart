/// Photo & Artwork Studio Screen.
/// 3 dithering algorithms, 5 quality presets, edge sharpening,
/// contrast curve, brightness, and real-time 384px thermal preview.
library;

import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:image/image.dart' as img;

import '../../core/ble_printer_manager.dart';
import '../../engine/photo_processor.dart';
import '../../ui/widgets/liquid_glass.dart';
import '../printer_settings/printer_dialog.dart';

class PhotoStudioScreen extends StatefulWidget {
  const PhotoStudioScreen({super.key});

  @override
  State<PhotoStudioScreen> createState() => _PhotoStudioScreenState();
}

class _PhotoStudioScreenState extends State<PhotoStudioScreen> {
  final BlePrinterManager _ble = BlePrinterManager();
  final ImagePicker _picker = ImagePicker();

  img.Image? _rawImage;
  img.Image? _processedThermalImage;
  Uint8List? _previewPngBytes;

  String _preset = 'portrait';
  String _dither = 'floyd';
  double _sharpness = 1.2;
  double _contrast = 1.12;
  double _brightness = 1.08;
  bool _autocrop = true;
  int _strength = 4;

  bool _isPreparing = false;
  String? _statusMessage;
  bool _isProcessing = false;
  bool _isPrinting = false;
  Timer? _debounceTimer;

  @override
  void dispose() {
    _debounceTimer?.cancel();
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      setState(() {
        _isPreparing = true;
        _statusMessage = source == ImageSource.camera
            ? 'Opening camera...'
            : 'Opening photo gallery...';
      });

      final XFile? file = await _picker.pickImage(source: source);
      if (file == null) {
        if (mounted) {
          setState(() {
            _isPreparing = false;
            _statusMessage = null;
          });
        }
        return;
      }

      if (mounted) {
        setState(() {
          _statusMessage = 'Reading image file...';
        });
      }

      final bytes = await file.readAsBytes();

      if (mounted) {
        setState(() {
          _statusMessage = 'Optimizing resolution & dither matrix...';
        });
      }

      final decodeInput = PhotoDecodeInput(
        bytes: bytes,
        preset: _preset,
        ditherAlgo: _dither,
        sharpness: _sharpness,
        contrast: _contrast,
        brightness: _brightness,
        autocrop: _autocrop,
        strength: _strength,
      );

      // Safe top-level isolate worker via compute() with no closure capture
      final result = await compute(runPhotoDecodeIsolate, decodeInput);

      if (result == null) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Failed to decode image file')),
          );
        }
        return;
      }

      if (mounted) {
        setState(() {
          _rawImage = result.rawImage;
          _processedThermalImage = result.processedImage;
          _previewPngBytes = result.pngBytes;
          _isPreparing = false;
          _statusMessage = null;
        });
      }
    } catch (e) {
      debugPrint('Error picking photo: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error loading photo: $e')),
        );
      }
    } finally {
      if (mounted && _isPreparing) {
        setState(() {
          _isPreparing = false;
          _statusMessage = null;
        });
      }
    }
  }

  void _clearPhoto() {
    _debounceTimer?.cancel();
    setState(() {
      _rawImage = null;
      _processedThermalImage = null;
      _previewPngBytes = null;
      _isPreparing = false;
      _isProcessing = false;
    });
  }

  void _onPresetChanged(String newPreset) {
    _preset = newPreset;
    final cfg = kPhotoPresets[newPreset] ?? kPhotoPresets['portrait']!;

    setState(() {
      _dither = cfg.dither;
      _sharpness = cfg.sharpness;
      _contrast = cfg.contrast;
      _brightness = cfg.brightness;
    });

    _updateLivePreview();
  }

  void _resetTuningToPreset() {
    final cfg = kPhotoPresets[_preset] ?? kPhotoPresets['portrait']!;
    setState(() {
      _sharpness = cfg.sharpness;
      _contrast = cfg.contrast;
      _brightness = cfg.brightness;
      _autocrop = true;
    });
    _schedulePreviewUpdate();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Tuning reset to ${cfg.title} defaults'),
          duration: const Duration(seconds: 1),
        ),
      );
    }
  }

  void _schedulePreviewUpdate() {
    if (_rawImage == null) return;
    _debounceTimer?.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 100), () {
      _updateLivePreview();
    });
  }

  Future<void> _updateLivePreview() async {
    if (_rawImage == null) return;

    setState(() => _isProcessing = true);

    final processInput = PhotoProcessInput(
      image: _rawImage!,
      preset: _preset,
      ditherAlgo: _dither,
      sharpness: _sharpness,
      contrast: _contrast,
      brightness: _brightness,
      autocrop: _autocrop,
      strength: _strength,
    );

    try {
      final result = await compute(runPhotoProcessingIsolate, processInput);

      if (mounted) {
        setState(() {
          _processedThermalImage = result.processedImage;
          _previewPngBytes = result.pngBytes;
          _isProcessing = false;
        });
      }
    } catch (e) {
      debugPrint('Error updating live preview: $e');
      if (mounted) {
        setState(() => _isProcessing = false);
      }
    }
  }

  void _showFullscreenPreview() {
    if (_previewPngBytes == null) return;
    showDialog(
      context: context,
      builder: (ctx) {
        return Dialog(
          backgroundColor: Colors.grey.shade900,
          insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '384px Thermal Dot Preview',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 16,
                          ),
                        ),
                        Text(
                          '${_processedThermalImage?.width ?? 384} × ${_processedThermalImage?.height ?? 0} dots • 1-bit monochrome',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ],
                ),
              ),
              const Divider(color: Colors.white24, height: 1),
              Flexible(
                child: Container(
                  color: const Color(0xFF141414),
                  constraints: const BoxConstraints(maxHeight: 460),
                  child: InteractiveViewer(
                    minScale: 0.5,
                    maxScale: 6.0,
                    child: Center(
                      child: Container(
                        margin: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withAlpha(120),
                              blurRadius: 10,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                        child: Image.memory(
                          _previewPngBytes!,
                          fit: BoxFit.contain,
                          filterQuality: FilterQuality.none, // Pixelated thermal pins
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const Divider(color: Colors.white24, height: 1),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Pinch or drag to inspect dots',
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                    ),
                    FilledButton.icon(
                      style: FilledButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                      ),
                      icon: const Icon(Icons.print, size: 16),
                      label: const Text('Print Now'),
                      onPressed: () {
                        Navigator.pop(ctx);
                        _handlePrint();
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _handlePrint() async {
    if (_processedThermalImage == null) return;

    if (!_ble.isConnected) {
      PrinterSelectionSheet.show(context);
      return;
    }

    setState(() => _isPrinting = true);

    try {
      await _ble.printImage(_processedThermalImage!, strength: _strength);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Photo printed successfully!')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Print failed: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isPrinting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListenableBuilder(
      listenable: _ble,
      builder: (context, _) {
        final isConnected = _ble.isConnected;

        return SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Photo Source & Thermal Preview Box
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Live 384px Thermal Preview',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (_previewPngBytes != null) ...[
                                IconButton(
                                  icon: const Icon(Icons.zoom_in, color: Colors.blue),
                                  tooltip: 'Inspect Thermal Dots',
                                  visualDensity: VisualDensity.compact,
                                  onPressed: _showFullscreenPreview,
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                                  tooltip: 'Remove Photo',
                                  visualDensity: VisualDensity.compact,
                                  onPressed: _clearPhoto,
                                ),
                              ],
                              IconButton(
                                icon: const Icon(Icons.photo_library),
                                tooltip: 'Gallery',
                                visualDensity: VisualDensity.compact,
                                onPressed: _isPreparing ? null : () => _pickImage(ImageSource.gallery),
                              ),
                              IconButton(
                                icon: const Icon(Icons.camera_alt),
                                tooltip: 'Camera',
                                visualDensity: VisualDensity.compact,
                                onPressed: _isPreparing ? null : () => _pickImage(ImageSource.camera),
                              ),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),

                      // Preview, Preparing Loader, or Dropzone Placeholder
                      if (_isPreparing)
                        Container(
                          height: 200,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: theme.scaffoldBackgroundColor,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: Colors.blue.withAlpha(120),
                            ),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const SizedBox(
                                width: 36,
                                height: 36,
                                child: CircularProgressIndicator(strokeWidth: 3),
                              ),
                              const SizedBox(height: 14),
                              Text(
                                _statusMessage ?? 'Preparing photo for thermal print...',
                                style: const TextStyle(fontWeight: FontWeight.bold),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Downscaling & generating live 384-dot dither...',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Colors.grey.shade600,
                                ),
                              ),
                            ],
                          ),
                        )
                      else if (_previewPngBytes != null) ...[
                        InkWell(
                          onTap: _showFullscreenPreview,
                          borderRadius: BorderRadius.circular(8),
                          child: Container(
                            constraints: const BoxConstraints(maxHeight: 260),
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: Colors.grey.withAlpha(80)),
                            ),
                            child: Stack(
                              alignment: Alignment.center,
                              children: [
                                Image.memory(
                                  _previewPngBytes!,
                                  fit: BoxFit.contain,
                                  filterQuality: FilterQuality.none, // Pixelated
                                ),
                                if (_isProcessing)
                                  Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: Colors.black54,
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: const SizedBox(
                                      width: 24,
                                      height: 24,
                                      child: CircularProgressIndicator(
                                        color: Colors.white,
                                        strokeWidth: 2.5,
                                      ),
                                    ),
                                  ),
                                Positioned(
                                  bottom: 4,
                                  right: 4,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: Colors.black87,
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: const Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.zoom_in, size: 12, color: Colors.white70),
                                        SizedBox(width: 4),
                                        Text(
                                          'Tap to inspect',
                                          style: TextStyle(color: Colors.white70, fontSize: 10),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              TextButton.icon(
                                style: TextButton.styleFrom(
                                  foregroundColor: Colors.redAccent,
                                  visualDensity: VisualDensity.compact,
                                ),
                                icon: const Icon(Icons.delete_outline, size: 16),
                                label: const Text('Remove Photo'),
                                onPressed: _clearPhoto,
                              ),
                              TextButton.icon(
                                style: TextButton.styleFrom(
                                  visualDensity: VisualDensity.compact,
                                ),
                                icon: const Icon(Icons.fullscreen, size: 16),
                                label: const Text('Inspect Full Dots'),
                                onPressed: _showFullscreenPreview,
                              ),
                            ],
                          ),
                        ),
                      ]
                      else
                        InkWell(
                          onTap: () => _pickImage(ImageSource.gallery),
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            height: 180,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: theme.scaffoldBackgroundColor,
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: Colors.grey.withAlpha(80),
                                style: BorderStyle.solid,
                              ),
                            ),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(
                                  Icons.add_photo_alternate,
                                  size: 42,
                                  color: Colors.blue,
                                ),
                                const SizedBox(height: 8),
                                const Text(
                                  'Tap to Select or Capture Photo',
                                  style: TextStyle(fontWeight: FontWeight.bold),
                                ),
                                Text(
                                  'Auto-scales to 384 thermal dots',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey.shade600,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              const SizedBox(height: 12),

              // Presets & Dithering Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Preset & Halftone Algorithm',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Preset Selector
                      DropdownButtonFormField<String>(
                        key: ValueKey(_preset),
                        initialValue: _preset,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Photo Style Preset',
                          isDense: true,
                          prefixIcon: Icon(Icons.auto_awesome, color: Colors.amber),
                        ),
                        items: kPhotoPresets.values.map((p) {
                          return DropdownMenuItem<String>(
                            value: p.key,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(p.title, style: const TextStyle(fontWeight: FontWeight.w600)),
                                Text(
                                  p.description,
                                  style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          );
                        }).toList(),
                        onChanged: (val) {
                          if (val != null) _onPresetChanged(val);
                        },
                      ),
                      const SizedBox(height: 16),

                      // 3 Dithering Algorithms (Matching Web Console)
                      DropdownButtonFormField<String>(
                        key: ValueKey(_dither),
                        initialValue: _dither,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Dithering Algorithm',
                          isDense: true,
                          prefixIcon: Icon(Icons.grid_3x3, color: Colors.blue),
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'floyd',
                            child: Text(
                              'Floyd-Steinberg (Ultra-Smooth Diffusion)',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          DropdownMenuItem(
                            value: 'atkinson',
                            child: Text(
                              'Atkinson (Apple Classic - Crisp Highlights)',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          DropdownMenuItem(
                            value: 'bayer',
                            child: Text(
                              'Bayer 8x8 (Ordered Matrix Halftone)',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                        onChanged: (val) {
                          if (val != null) {
                            setState(() => _dither = val);
                            _schedulePreviewUpdate();
                          }
                        },
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 12),

              // Detail Tuning Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Detail Tuning & Dynamic Range',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.refresh, size: 20),
                            tooltip: 'Reset detail tuning to preset defaults',
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                            onPressed: _resetTuningToPreset,
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),

                      // Edge Sharpening Slider
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Edge Sharpening:'),
                          Text('${(_sharpness * 100).toInt()}%'),
                        ],
                      ),
                      Slider(
                        value: _sharpness,
                        min: 0.0,
                        max: 2.5,
                        divisions: 25,
                        onChanged: (val) {
                          setState(() => _sharpness = val);
                          _schedulePreviewUpdate();
                        },
                      ),

                      // Contrast Curve Slider
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Contrast Curve:'),
                          Text('${((_contrast - 1.0) * 100).toInt() >= 0 ? '+' : ''}${((_contrast - 1.0) * 100).toInt()}%'),
                        ],
                      ),
                      Slider(
                        value: _contrast,
                        min: 0.8,
                        max: 1.5,
                        divisions: 14,
                        onChanged: (val) {
                          setState(() => _contrast = val);
                          _schedulePreviewUpdate();
                        },
                      ),

                      // Brightness / Shadow Lift Slider
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('Brightness / Shadow Lift:'),
                          Text('${((_brightness - 1.0) * 100).toInt() >= 0 ? '+' : ''}${((_brightness - 1.0) * 100).toInt()}%'),
                        ],
                      ),
                      Slider(
                        value: _brightness,
                        min: 0.85,
                        max: 1.25,
                        divisions: 8,
                        onChanged: (val) {
                          setState(() => _brightness = val);
                          _schedulePreviewUpdate();
                        },
                      ),

                      // Autocrop switch & Strength
                      Row(
                        children: [
                          Expanded(
                            child: SwitchListTile(
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Auto-crop White Margins'),
                              value: _autocrop,
                              onChanged: (val) {
                                setState(() => _autocrop = val);
                                _schedulePreviewUpdate();
                              },
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<int>(
                              initialValue: _strength,
                              isExpanded: true,
                              decoration: const InputDecoration(
                                labelText: 'Darkness',
                                isDense: true,
                              ),
                              items: const [
                                DropdownMenuItem(value: 1, child: Text('1 - Lightest')),
                                DropdownMenuItem(value: 2, child: Text('2 - Light')),
                                DropdownMenuItem(value: 3, child: Text('3 - Medium')),
                                DropdownMenuItem(value: 4, child: Text('4 - Normal')),
                                DropdownMenuItem(value: 5, child: Text('5 - Dark')),
                                DropdownMenuItem(value: 6, child: Text('6 - Very Dark')),
                                DropdownMenuItem(value: 7, child: Text('7 - Max Dark')),
                              ],
                              onChanged: (val) {
                                if (val != null) setState(() => _strength = val);
                              },
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 18),

              // Actions (when photo loaded)
              if (_previewPngBytes != null) ...[
                Row(
                  children: [
                    Expanded(
                      flex: 4,
                      child: OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.redAccent,
                          side: BorderSide(color: Colors.redAccent.withAlpha(140)),
                        ),
                        icon: const Icon(Icons.delete_outline, size: 18),
                        label: const Text('Remove', maxLines: 1),
                        onPressed: _clearPhoto,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      flex: 6,
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.fullscreen, size: 18),
                        label: const Text('Inspect Dots', maxLines: 1),
                        onPressed: _showFullscreenPreview,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
              ],

              // Print Photo Button
              ElevatedButton.icon(
                icon: _isPrinting
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 2,
                        ),
                      )
                    : const Icon(Icons.print),
                label: Text(_isPrinting ? 'Printing Photo...' : 'Print Dithered Photo'),
                onPressed: (_isPrinting || _processedThermalImage == null)
                    ? null
                    : _handlePrint,
              ),

              if (!isConnected) ...[
                const SizedBox(height: 8),
                Text(
                  '⚠️ Thermal printer not connected. Tap button above to pair.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: theme.colorScheme.error,
                    fontSize: 12,
                  ),
                ),
              ],
              const SizedBox(height: 28),
            ],
          ),
        );
      },
    );
  }
}
