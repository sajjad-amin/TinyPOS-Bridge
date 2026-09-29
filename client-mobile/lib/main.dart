import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'core/ble_printer_manager.dart';
import 'core/storage_service.dart';
import 'core/websocket_relay.dart';
import 'features/cloud_bridge/cloud_bridge_screen.dart';
import 'features/file_print/file_print_screen.dart';
import 'features/photo_studio/photo_studio_screen.dart';
import 'features/qr_print/qr_print_screen.dart';
import 'features/text_print/text_print_screen.dart';
import 'ui/theme.dart';
import 'ui/widgets/printer_status_bar.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize persistent storage and core hardware singletons
  final storage = await StorageService.init();
  final bleManager = BlePrinterManager();
  bleManager.init(storage);

  final relay = WebSocketRelayService();
  relay.init(storage, bleManager);

  runApp(TinyPOSMobileApp(storage: storage));
}

class TinyPOSMobileApp extends StatelessWidget {
  final StorageService storage;

  const TinyPOSMobileApp({super.key, required this.storage});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TinyPOS',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: MainShellScreen(storage: storage),
    );
  }
}

class MainShellScreen extends StatefulWidget {
  final StorageService storage;

  const MainShellScreen({super.key, required this.storage});

  @override
  State<MainShellScreen> createState() => _MainShellScreenState();
}

class _MainShellScreenState extends State<MainShellScreen> {
  int _currentIndex = 0;

  late final List<Widget> _screens;

  @override
  void initState() {
    super.initState();
    _screens = [
      const TextPrintScreen(),
      const PhotoStudioScreen(),
      const QrPrintScreen(),
      const FilePrintScreen(),
      CloudBridgeScreen(storage: widget.storage),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isIOS = defaultTargetPlatform == TargetPlatform.iOS;
    final isDark = theme.brightness == Brightness.dark;

    const titles = [
      'Print Text & Notes',
      'Photo & Artwork Studio',
      'Thermal QR Code',
      'Print PDF & Invoices',
      'Cloud Relay Bridge',
    ];

    final navBar = NavigationBar(
      backgroundColor: isIOS ? Colors.transparent : null,
      elevation: isIOS ? 0 : null,
      selectedIndex: _currentIndex,
      onDestinationSelected: (index) {
        setState(() => _currentIndex = index);
      },
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.text_fields),
          selectedIcon: Icon(Icons.text_fields, color: Colors.blue),
          label: 'Text',
        ),
        NavigationDestination(
          icon: Icon(Icons.photo_filter),
          selectedIcon: Icon(Icons.photo_filter, color: Colors.blue),
          label: 'Photo',
        ),
        NavigationDestination(
          icon: Icon(Icons.qr_code_2),
          selectedIcon: Icon(Icons.qr_code_2, color: Colors.blue),
          label: 'QR Code',
        ),
        NavigationDestination(
          icon: Icon(Icons.picture_as_pdf),
          selectedIcon: Icon(Icons.picture_as_pdf, color: Colors.blue),
          label: 'Document',
        ),
        NavigationDestination(
          icon: Icon(Icons.cloud_sync),
          selectedIcon: Icon(Icons.cloud_sync, color: Colors.blue),
          label: 'Cloud Relay',
        ),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        backgroundColor: isIOS
            ? (isDark
                ? const Color(0xFF1E293B).withAlpha(200)
                : Colors.white.withAlpha(220))
            : null,
        title: Row(
          children: [
            const Icon(Icons.print, color: Colors.blue, size: 24),
            const SizedBox(width: 8),
            Text(titles[_currentIndex]),
          ],
        ),
        bottom: const PrinterStatusBar(),
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: isIOS
          ? ClipRect(
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                child: Container(
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF1E293B).withAlpha(190)
                        : Colors.white.withAlpha(205),
                    border: Border(
                      top: BorderSide(
                        color: isDark
                            ? Colors.white.withAlpha(25)
                            : Colors.white.withAlpha(120),
                        width: 1.0,
                      ),
                    ),
                  ),
                  child: navBar,
                ),
              ),
            )
          : navBar,
    );
  }
}
