import 'package:flutter/material.dart';

abstract class AppColors {
  // Primary brand
  static const Color primary = Color(0xFF6366F1);       // indigo-500
  static const Color primaryDark = Color(0xFF4F46E5);   // indigo-600
  static const Color primaryLight = Color(0xFF818CF8);  // indigo-400

  // Surface (dark theme)
  static const Color backgroundDark = Color(0xFF0F172A); // slate-900
  static const Color surfaceDark = Color(0xFF1E293B);    // slate-800
  static const Color cardDark = Color(0xFF334155);       // slate-700

  // Surface (light theme)
  static const Color backgroundLight = Color(0xFFF8FAFC); // slate-50
  static const Color surfaceLight = Color(0xFFFFFFFF);
  static const Color cardLight = Color(0xFFF1F5F9);       // slate-100

  // Status
  static const Color success = Color(0xFF22C55E);  // green-500
  static const Color error = Color(0xFFEF4444);    // red-500
  static const Color warning = Color(0xFFF59E0B);  // amber-500
  static const Color info = Color(0xFF3B82F6);     // blue-500

  // Text
  static const Color textPrimary = Color(0xFFF1F5F9);
  static const Color textSecondary = Color(0xFF94A3B8);
  static const Color textMuted = Color(0xFF64748B);

  // Chart colors
  static const List<Color> chartPalette = [
    Color(0xFF6366F1), // indigo
    Color(0xFF22C55E), // green
    Color(0xFFF59E0B), // amber
    Color(0xFF3B82F6), // blue
    Color(0xFFEC4899), // pink
    Color(0xFF8B5CF6), // violet
    Color(0xFF14B8A6), // teal
    Color(0xFFF97316), // orange
  ];
}
