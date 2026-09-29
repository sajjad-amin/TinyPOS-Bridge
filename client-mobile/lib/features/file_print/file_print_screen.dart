/// Direct PDF & Image File Print Screen.
/// Supports PDF invoices, receipts, and images with auto-scaling to 384 dots,
/// upfront rasterization progress, crisp document mode vs photo dither mode,
/// and live 384-dot receipt preview.
library;

import 'dart:io';
import 'dart:typed_data';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;

import '../../core/bainiu_protocol.dart';
import '../../core/ble_printer_manager.dart';
import '../../engine/pdf_processor.dart';
import '../../ui/widgets/liquid_glass.dart';
import '../printer_settings/printer_dialog.dart';

class FilePrintScreen extends StatefulWidget {
  const FilePrintScreen({super.key});

  @override
  State<FilePrintScreen> createState() => _FilePrintScreenState();
}

class _FilePrintScreenState extends State<FilePrintScreen> {
  final BlePrinterManager _ble = BlePrinterManager();

  File? _selectedFile;
  String? _fileName;
  bool _isPdf = false;

  bool _isPreparing = false;
  String? _statusText;
  bool _isPrinting = false;

  bool _autocrop = true;
  bool _dither = false; // Default: crisp binarization for receipts/invoices
  int _strength = 7; // Default: Max Dark (7) matching Web file printing

  List<img.Image> _preparedPages = [];
  Uint8List? _previewPngBytes;

  Future<void> _pickFile() async {
    try {
      final files = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['pdf', 'png', 'jpg', 'jpeg', 'webp'],
      );

      if (files.isEmpty || files.first.path == null) return;

      final file = File(files.first.path!);
      final name = files.first.name;
      final isPdf = name.toLowerCase().endsWith('.pdf');

      setState(() {
        _selectedFile = file;
        _fileName = name;
        _isPdf = isPdf;
        _preparedPages = [];
        _previewPngBytes = null;
      });

      await _prepareDocument();
    } catch (e) {
      debugPrint('Error picking file: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error choosing file: $e')),
        );
      }
    }
  }

  void _clearFile() {
    setState(() {
      _selectedFile = null;
      _fileName = null;
      _isPdf = false;
      _preparedPages = [];
      _previewPngBytes = null;
      _isPreparing = false;
      _statusText = null;
    });
  }

  Future<void> _prepareDocument() async {
    if (_selectedFile == null) return;

    setState(() {
      _isPreparing = true;
      _statusText = _isPdf ? 'Opening PDF & rasterizing pages...' : 'Scaling image to 384 dots...';
    });

    try {
      final params = getStrengthParams(_strength);

      if (_isPdf) {
        final pages = await PdfProcessor.processPdfFile(
          _selectedFile!.path,
          autocrop: _autocrop,
          dither: _dither,
          strength: _strength,
          threshold: params.threshold,
          onProgress: (cur, total) {
            if (mounted) {
              setState(() {
                _statusText = 'Rasterizing page $cur of $total...';
              });
            }
          },
        );

        if (pages.isEmpty) {
          throw Exception('No printable pages rendered from PDF');
        }

        final pngBytes = Uint8List.fromList(img.encodePng(pages.first));

        if (mounted) {
          setState(() {
            _preparedPages = pages;
            _previewPngBytes = pngBytes;
            _isPreparing = false;
            _statusText = null;
          });
        }
      } else {
        setState(() => _statusText = 'Preparing image for thermal print...');
        final image = await PdfProcessor.processImageFile(
          _selectedFile!,
          autocrop: _autocrop,
          dither: _dither,
          strength: _strength,
          threshold: params.threshold,
        );

        final pngBytes = Uint8List.fromList(img.encodePng(image));

        if (mounted) {
          setState(() {
            _preparedPages = [image];
            _previewPngBytes = pngBytes;
            _isPreparing = false;
            _statusText = null;
          });
        }
      }
    } catch (e) {
      debugPrint('Error preparing document: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Document preparation failed: $e')),
        );
      }
    } finally {
      if (mounted && _isPreparing) {
        setState(() {
          _isPreparing = false;
          _statusText = null;
        });
      }
    }
  }

  Future<void> _handlePrint() async {
    if (_preparedPages.isEmpty) {
      await _prepareDocument();
      if (_preparedPages.isEmpty || !mounted) return;
    }

    if (!mounted) return;
    if (!_ble.isConnected) {
      PrinterSelectionSheet.show(context);
      return;
    }

    setState(() {
      _isPrinting = true;
      _statusText = 'Starting thermal print...';
    });

    try {
      final totalPages = _preparedPages.length;
      for (int i = 0; i < totalPages; i++) {
        if (!mounted) break;
        setState(() {
          _statusText = 'Printing page ${i + 1} of $totalPages...';
        });

        await _ble.printImage(_preparedPages[i], strength: _strength);

        // Pause between multi-page documents to let paper feed & cooling occur
        if (i < totalPages - 1) {
          await Future.delayed(const Duration(milliseconds: 600));
        }
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              totalPages > 1
                  ? 'All $totalPages pages printed successfully!'
                  : 'Document printed successfully!',
            ),
          ),
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
        setState(() {
          _isPrinting = false;
          _statusText = null;
        });
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
                          'Thermal Roll Preview (Page 1)',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                            fontSize: 16,
                          ),
                        ),
                        Text(
                          '${_preparedPages.first.width} × ${_preparedPages.first.height} dots • ${_isPdf ? '$_preparedPages.length total pages' : 'Single document'}',
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
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
                          filterQuality: FilterQuality.none,
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
                      'Pinch or zoom to inspect text clarity',
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
              // Document Source Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Document Source',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          if (_selectedFile != null)
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                TextButton.icon(
                                  icon: const Icon(Icons.swap_horiz, size: 16),
                                  label: const Text('Change'),
                                  onPressed: (_isPreparing || _isPrinting) ? null : _pickFile,
                                ),
                                IconButton(
                                  icon: const Icon(Icons.close, color: Colors.grey, size: 18),
                                  tooltip: 'Clear',
                                  onPressed: (_isPreparing || _isPrinting) ? null : _clearFile,
                                ),
                              ],
                            ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      if (_isPreparing)
                        Container(
                          height: 150,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: theme.scaffoldBackgroundColor,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: Colors.blue.withAlpha(120)),
                          ),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const SizedBox(
                                width: 34,
                                height: 34,
                                child: CircularProgressIndicator(strokeWidth: 3),
                              ),
                              const SizedBox(height: 14),
                              Text(
                                _statusText ?? 'Rasterizing document pages...',
                                style: const TextStyle(fontWeight: FontWeight.bold),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Formatting for 57mm (384-dot) thermal paper...',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                        )
                      else if (_selectedFile != null)
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: theme.scaffoldBackgroundColor,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(color: Colors.grey.withAlpha(60)),
                          ),
                          child: Column(
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    _isPdf ? Icons.picture_as_pdf : Icons.image,
                                    size: 40,
                                    color: _isPdf ? Colors.red : Colors.blue,
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          _fileName ?? '',
                                          style: const TextStyle(fontWeight: FontWeight.bold),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          _preparedPages.isNotEmpty
                                              ? '📄 ${_preparedPages.length} ${_preparedPages.length == 1 ? "page" : "pages"} ready • 384 dots width'
                                              : 'Processing...',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: Colors.green.shade700,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),

                              // Preview thumbnail box if available
                              if (_previewPngBytes != null) ...[
                                const SizedBox(height: 12),
                                const Divider(),
                                const SizedBox(height: 6),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const Text(
                                      'Thermal Preview:',
                                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                                    ),
                                    TextButton.icon(
                                      style: TextButton.styleFrom(
                                        visualDensity: VisualDensity.compact,
                                      ),
                                      icon: const Icon(Icons.fullscreen, size: 16),
                                      label: const Text('Inspect Dots'),
                                      onPressed: _showFullscreenPreview,
                                    ),
                                  ],
                                ),
                                InkWell(
                                  onTap: _showFullscreenPreview,
                                  child: Container(
                                    height: 140,
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(8),
                                    decoration: BoxDecoration(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: Colors.grey.withAlpha(80)),
                                    ),
                                    child: Image.memory(
                                      _previewPngBytes!,
                                      fit: BoxFit.contain,
                                      filterQuality: FilterQuality.none,
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                        )
                      else
                        InkWell(
                          onTap: _pickFile,
                          borderRadius: BorderRadius.circular(10),
                          child: Container(
                            height: 160,
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
                                  Icons.upload_file,
                                  size: 42,
                                  color: Colors.blue,
                                ),
                                const SizedBox(height: 8),
                                const Text(
                                  'Tap to Select PDF or Image Invoice',
                                  style: TextStyle(fontWeight: FontWeight.bold),
                                ),
                                Text(
                                  'PDF, PNG, JPG • Auto-scaled to 57mm roll',
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

              // Options Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Thermal Print Options',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.refresh, size: 20),
                          tooltip: 'Reset to Web Defaults',
                          onPressed: () {
                            setState(() {
                              _strength = 7;
                              _autocrop = true;
                              _dither = false;
                            });
                            if (_selectedFile != null) _prepareDocument();
                          },
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),

                      // Print Mode: Crisp Document vs Photo Dither
                      DropdownButtonFormField<bool>(
                        initialValue: _dither,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Print Quality Mode',
                          isDense: true,
                          prefixIcon: Icon(Icons.style, color: Colors.blue),
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: false,
                            child: Text(
                              'Document Mode (Crisp Text & Tables)',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          DropdownMenuItem(
                            value: true,
                            child: Text(
                              'Photo Dither Mode (Halftone for Artwork)',
                              style: TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                        onChanged: (val) {
                          if (val != null && val != _dither) {
                            setState(() => _dither = val);
                            if (_selectedFile != null) _prepareDocument();
                          }
                        },
                      ),
                      const SizedBox(height: 12),

                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Auto-crop White Margins'),
                        subtitle: const Text(
                          'Removes empty A4 borders to maximize receipt width',
                          style: TextStyle(fontSize: 12),
                        ),
                        value: _autocrop,
                        onChanged: (val) {
                          setState(() => _autocrop = val);
                          if (_selectedFile != null) _prepareDocument();
                        },
                      ),
                      const Divider(),

                      DropdownButtonFormField<int>(
                        initialValue: _strength,
                        isExpanded: true,
                        decoration: const InputDecoration(
                          labelText: 'Print Darkness / Contrast',
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
                          if (val != null) {
                            setState(() => _strength = val);
                            if (_selectedFile != null) _prepareDocument();
                          }
                        },
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 18),

              // Print File Button
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
                label: Text(
                  _isPrinting
                      ? (_statusText ?? 'Printing...')
                      : (_selectedFile == null
                          ? 'Select a Document'
                          : (_preparedPages.length > 1
                              ? 'Print ${_preparedPages.length} Pages'
                              : 'Print Document')),
                ),
                onPressed: (_isPrinting || _isPreparing || _selectedFile == null)
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
