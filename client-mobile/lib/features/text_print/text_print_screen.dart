/// Multilingual Free-form Text Print Screen.
/// Supports any world script (Bengali, Arabic RTL, Chinese, Hindi, etc.) and emojis.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;

import '../../core/ble_printer_manager.dart';
import '../../engine/canvas_rasterizer.dart';
import '../../ui/widgets/liquid_glass.dart';
import '../printer_settings/printer_dialog.dart';

class TextPrintScreen extends StatefulWidget {
  const TextPrintScreen({super.key});

  @override
  State<TextPrintScreen> createState() => _TextPrintScreenState();
}

class _TextPrintScreenState extends State<TextPrintScreen> {
  final TextEditingController _textCtrl = TextEditingController();
  final BlePrinterManager _ble = BlePrinterManager();

  final FocusNode _focusNode = FocusNode();

  double _fontSize = 24.0;
  TextAlign _textAlign = TextAlign.left;
  bool _isBold = false;
  int _strength = 4;
  bool _isPrinting = false;
  bool _isPreviewing = false;

  @override
  void initState() {
    super.initState();
    _focusNode.addListener(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _textCtrl.dispose();
    super.dispose();
  }

  Future<void> _pasteFromClipboard() async {
    final data = await Clipboard.getData('text/plain');
    if (data?.text != null && data!.text!.isNotEmpty) {
      setState(() {
        _textCtrl.text = data.text!;
      });
    }
  }

  void _resetFormattingToDefaults() {
    setState(() {
      _fontSize = 24.0;
      _textAlign = TextAlign.left;
      _isBold = false;
      _strength = 4;
    });
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Formatting reset to defaults (24pt, Left, Normal, Strength 4)'),
          duration: Duration(seconds: 1),
        ),
      );
    }
  }

  Future<void> _showBitmapPreview() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter text to preview')),
      );
      return;
    }

    setState(() => _isPreviewing = true);

    try {
      final bitmap = await renderTextToBitmap(
        text: text,
        options: TextRenderOptions(
          fontSize: _fontSize,
          textAlign: _textAlign,
          isBold: _isBold,
          lineSpacing: 1.25,
        ),
      );

      final pngBytes = Uint8List.fromList(img.encodePng(bitmap));

      if (!mounted) return;

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
                            '384px Thermal Text Preview',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                            ),
                          ),
                          Text(
                            '${bitmap.width} × ${bitmap.height} dots • 1-bit monochrome',
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
                            pngBytes,
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.none, // Preserve 1-bit thermal pins
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
                        'Pinch to zoom thermal dots',
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
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Preview error: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isPreviewing = false);
      }
    }
  }

  Future<void> _handlePrint() async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter text to print')),
      );
      return;
    }

    if (!_ble.isConnected) {
      PrinterSelectionSheet.show(context);
      return;
    }

    setState(() => _isPrinting = true);

    try {
      final bitmap = await renderTextToBitmap(
        text: text,
        options: TextRenderOptions(
          fontSize: _fontSize,
          textAlign: _textAlign,
          isBold: _isBold,
          lineSpacing: 1.25,
        ),
      );

      await _ble.printImage(bitmap, strength: _strength);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Receipt printed successfully!')),
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

        final isKeyboardOpen =
            _focusNode.hasFocus || MediaQuery.of(context).viewInsets.bottom > 0;

        return GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTap: () {
            if (_focusNode.hasFocus) {
              _focusNode.unfocus();
            }
          },
          child: SingleChildScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Text Input Card
                LiquidGlass(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Text & Note Content',
                              style: theme.textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (isKeyboardOpen)
                                  Padding(
                                    padding: const EdgeInsets.only(right: 6),
                                    child: FilledButton.tonalIcon(
                                      style: FilledButton.styleFrom(
                                        visualDensity: VisualDensity.compact,
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 10, vertical: 2),
                                        backgroundColor: Colors.blue.withAlpha(35),
                                        foregroundColor: Colors.blue,
                                      ),
                                      icon: const Icon(Icons.keyboard_hide, size: 16),
                                      label: const Text(
                                        'Done',
                                        style: TextStyle(
                                            fontWeight: FontWeight.bold,
                                            fontSize: 12),
                                      ),
                                      onPressed: () => _focusNode.unfocus(),
                                    ),
                                  ),
                                IconButton(
                                  icon: _isPreviewing
                                      ? const SizedBox(
                                          width: 14,
                                          height: 14,
                                          child: CircularProgressIndicator(
                                              strokeWidth: 2),
                                        )
                                      : const Icon(Icons.visibility_outlined,
                                          size: 20),
                                  tooltip: 'Preview Bitmap',
                                  visualDensity: VisualDensity.compact,
                                  onPressed: (_isPreviewing ||
                                          _textCtrl.text.trim().isEmpty)
                                      ? null
                                      : _showBitmapPreview,
                                ),
                                IconButton(
                                  icon: const Icon(Icons.paste_outlined, size: 20),
                                  tooltip: 'Paste',
                                  visualDensity: VisualDensity.compact,
                                  onPressed: _pasteFromClipboard,
                                ),
                                if (_textCtrl.text.isNotEmpty)
                                  IconButton(
                                    icon: const Icon(Icons.clear, size: 20),
                                    tooltip: 'Clear',
                                    visualDensity: VisualDensity.compact,
                                    onPressed: () =>
                                        setState(() => _textCtrl.clear()),
                                  ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),

                        TextField(
                          controller: _textCtrl,
                          focusNode: _focusNode,
                          maxLines: 8,
                          minLines: 4,
                          onChanged: (_) => setState(() {}),
                          decoration: const InputDecoration(
                            hintText:
                                'Enter text, notes, tasks, or paste content to print...',
                          ),
                        ),
                        if (isKeyboardOpen) ...[
                          const SizedBox(height: 8),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                '${_textCtrl.text.length} characters • ${_textCtrl.text.isEmpty ? 0 : _textCtrl.text.split('\n').length} lines',
                                style: TextStyle(
                                    fontSize: 11, color: Colors.grey.shade500),
                              ),
                              TextButton.icon(
                                style: TextButton.styleFrom(
                                  visualDensity: VisualDensity.compact,
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 8, vertical: 2),
                                ),
                                icon: const Icon(Icons.keyboard_hide_outlined,
                                    size: 16),
                                label: const Text(
                                  'Hide Keyboard',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w600, fontSize: 12),
                                ),
                                onPressed: () => _focusNode.unfocus(),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                const SizedBox(height: 12),

              // Typography & Layout Controls Card
              LiquidGlass(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Formatting & Print Quality',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.refresh, size: 20),
                            tooltip: 'Reset formatting to defaults',
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                            onPressed: _resetFormattingToDefaults,
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),

                      // Font Size Slider
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Font Size:',
                            style: TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.blue.withAlpha(30),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              '${_fontSize.toInt()} pt',
                              style: const TextStyle(
                                fontWeight: FontWeight.bold,
                                color: Colors.blue,
                              ),
                            ),
                          ),
                        ],
                      ),
                      Slider(
                        value: _fontSize,
                        min: 16.0,
                        max: 60.0,
                        divisions: 22,
                        label: '${_fontSize.toInt()} pt',
                        onChanged: (val) {
                          setState(() => _fontSize = val);
                        },
                      ),
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: [
                            const Text('Quick:', style: TextStyle(fontSize: 12, color: Colors.grey)),
                            const SizedBox(width: 8),
                            for (final size in [18.0, 24.0, 32.0, 44.0, 60.0])
                              Padding(
                                padding: const EdgeInsets.only(right: 6),
                                child: ChoiceChip(
                                  label: Text('${size.toInt()} pt'),
                                  selected: _fontSize.toInt() == size.toInt(),
                                  onSelected: (_) => setState(() => _fontSize = size),
                                  visualDensity: VisualDensity.compact,
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Alignment
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Alignment:',
                            style: TextStyle(fontWeight: FontWeight.w600),
                          ),
                          Row(
                            children: [
                              for (final item in [
                                (TextAlign.left, Icons.format_align_left, 'Left'),
                                (TextAlign.center, Icons.format_align_center, 'Center'),
                                (TextAlign.right, Icons.format_align_right, 'Right'),
                              ])
                                Expanded(
                                  child: Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 3),
                                    child: ChoiceChip(
                                      showCheckmark: false,
                                      label: SizedBox(
                                        height: 24,
                                        child: Center(child: Icon(item.$2, size: 20)),
                                      ),
                                      tooltip: item.$3,
                                      selected: _textAlign == item.$1,
                                      onSelected: (_) => setState(() => _textAlign = item.$1),
                                      visualDensity: VisualDensity.compact,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),

                      // Bold & Print Strength
                      Row(
                        children: [
                          Expanded(
                            child: InkWell(
                              onTap: () => setState(() => _isBold = !_isBold),
                              borderRadius: BorderRadius.circular(8),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(vertical: 4),
                                child: Row(
                                  children: [
                                    Checkbox(
                                      value: _isBold,
                                      onChanged: (val) => setState(() => _isBold = val ?? false),
                                      visualDensity: VisualDensity.compact,
                                    ),
                                    const Text(
                                      'Bold Font',
                                      style: TextStyle(fontWeight: FontWeight.w600),
                                    ),
                                  ],
                                ),
                              ),
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
                                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8),
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

              // Action Buttons: Preview Bitmap & Print
              Row(
                children: [
                  Expanded(
                    flex: 4,
                    child: OutlinedButton.icon(
                      icon: _isPreviewing
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.visibility_outlined, size: 18),
                      label: const Text('Preview', maxLines: 1),
                      onPressed: (_isPreviewing || _textCtrl.text.trim().isEmpty)
                          ? null
                          : _showBitmapPreview,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    flex: 6,
                    child: ElevatedButton.icon(
                      icon: _isPrinting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              ),
                            )
                          : const Icon(Icons.print, size: 18),
                      label: Text(_isPrinting ? 'Printing...' : 'Print Receipt', maxLines: 1),
                      onPressed: (_isPrinting || _textCtrl.text.trim().isEmpty)
                          ? null
                          : _handlePrint,
                    ),
                  ),
                ],
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
        ),
      );
    },
    );
  }
}
