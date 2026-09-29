/// Premium Frosted "Liquid Glass" (Glassmorphism) Component for iOS.
///
/// On iOS: Renders real-time hardware-accelerated frosted glass with backdrop blur,
/// translucent tint, specular sheen borders, and subtle depth shadows.
///
/// On Android & Other Platforms: Gracefully falls back to standard Material 3
/// surfaces, ensuring optimal performance and platform-native conventions.
library;

import 'dart:ui';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class LiquidGlass extends StatelessWidget {
  final Widget child;
  final double borderRadius;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final Color? tintColor;
  final double blurSigma;
  final Border? border;
  final bool forceGlass;
  final VoidCallback? onTap;

  const LiquidGlass({
    super.key,
    required this.child,
    this.borderRadius = 16.0,
    this.padding,
    this.margin,
    this.tintColor,
    this.blurSigma = 20.0,
    this.border,
    this.forceGlass = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isIOS = forceGlass || (defaultTargetPlatform == TargetPlatform.iOS);
    final isDark = theme.brightness == Brightness.dark;

    // --- Android & Fallback: Clean Native Material 3 Surface ---
    if (!isIOS) {
      final fallbackCard = Container(
        margin: margin,
        padding: padding,
        decoration: BoxDecoration(
          color: theme.cardTheme.color ?? theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(borderRadius),
          border: Border.all(
            color: isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
            width: 1.0,
          ),
        ),
        child: child,
      );

      if (onTap != null) {
        return InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(borderRadius),
          child: fallbackCard,
        );
      }
      return fallbackCard;
    }

    // --- iOS: Apple "Liquid Glass" Frosted Translucent Material ---
    // 72% opacity in light mode, 65% in dark mode
    final glassColor = tintColor ??
        (isDark
            ? const Color(0xFF1E293B).withAlpha(165)
            : Colors.white.withAlpha(185));

    // Specular light edge sheen
    final glassBorder = border ??
        Border.all(
          color: isDark
              ? Colors.white.withAlpha(35)
              : Colors.white.withAlpha(150),
          width: 1.2,
        );

    Widget glassContainer = Container(
      margin: margin,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
          child: Container(
            padding: padding,
            decoration: BoxDecoration(
              color: glassColor,
              borderRadius: BorderRadius.circular(borderRadius),
              border: glassBorder,
              boxShadow: [
                BoxShadow(
                  color: isDark
                      ? Colors.black.withAlpha(70)
                      : Colors.black.withAlpha(15),
                  blurRadius: 18,
                  offset: const Offset(0, 4),
                  spreadRadius: 0,
                ),
              ],
            ),
            child: child,
          ),
        ),
      ),
    );

    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        child: glassContainer,
      );
    }

    return glassContainer;
  }
}
