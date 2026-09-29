/// Hardware specifications and Bainiu thermal printer protocol constants.
library;

import 'dart:typed_data';

/// Standard 57mm thermal printer printable width in dots (384 pixels = 48 bytes per row).
const int kPrintWidth = 384;

/// Bainiu Protocol Header & Footer
final Uint8List kHeader = Uint8List.fromList([0x51, 0x78]);
const int kFooter = 0xFF;

/// Bainiu / Tiny Print BLE Service UUIDs
const List<String> kKnownServiceUuids = [
  '0000ae30-0000-1000-8000-00805f9b34fb',
  '0000af30-0000-1000-8000-00805f9b34fb',
  '0000ff00-0000-1000-8000-00805f9b34fb',
  '49535343-fe7d-4ae5-8fa9-9fafd205e455',
  'ae30',
  'af30',
  'ff00',
];

/// Bainiu / Tiny Print BLE TX Characteristic UUIDs (Write / WriteWithoutResponse)
const List<String> kKnownTxCharUuids = [
  '0000ae01-0000-1000-8000-00805f9b34fb',
  '0000ff02-0000-1000-8000-00805f9b34fb',
  '49535343-8841-43f4-a8d4-ecbe34729bb3',
  'ae01',
  'ff02',
];

/// Known BLE Device names matching Bainiu / Tiny Print family
const List<String> kKnownPrinterNames = [
  'x6',
  'tiny print',
  'tinyprint',
  'iprint',
  'pocket printer',
  'gb01',
  'gb02',
  'gb03',
  'gt01',
  'x5',
  'x7',
  'x2',
  'x1',
  'x8',
  'sc03',
  'rt034',
  'mx0',
  'c9',
  'c13',
  'c15',
  'c17',
  'c19',
  'c20',
  'c21',
  'c22',
  'c23',
  'ble_printer',
  'cat printer',
  'walkprint',
  'funprint',
  'luckjingle',
  'pos',
  'mpt',
  'printer',
];
