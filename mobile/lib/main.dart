import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/app.dart';
import 'package:investai_mobile/providers/core/storage_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await dotenv.load();

  final container = ProviderContainer();
  await container.read(storageProvider).init();

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const InvestAIApp(),
    ),
  );
}
