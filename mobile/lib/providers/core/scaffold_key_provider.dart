import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// Holds the callback to open the main shell's drawer
final drawerOpenerProvider = StateProvider<VoidCallback?>((ref) => null);
