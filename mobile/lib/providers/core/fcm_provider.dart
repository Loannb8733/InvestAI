import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:investai_mobile/core/services/fcm_service.dart';
import 'package:investai_mobile/providers/core/storage_provider.dart';

final fcmServiceProvider = Provider<FcmService>((ref) {
  return FcmService(ref.watch(storageProvider));
});
