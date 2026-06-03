import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:investai_mobile/core/constants/storage_keys.dart';
import 'package:investai_mobile/core/services/storage_service.dart';

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('Background FCM: ${message.notification?.title}');
}

class FcmService {
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications = FlutterLocalNotificationsPlugin();
  final StorageService _storage;

  FcmService(this._storage);

  Future<void> init() async {
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Request permissions
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    if (settings.authorizationStatus == AuthorizationStatus.authorized) {
      await _initLocalNotifications();
      await _saveToken();
      _listenForeground();
    }
  }

  Future<void> _initLocalNotifications() async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings();
    const settings = InitializationSettings(android: androidSettings, iOS: iosSettings);
    await _localNotifications.initialize(settings);
  }

  Future<void> _saveToken() async {
    final token = await _messaging.getToken();
    if (token != null) {
      await _storage.writeSecure(StorageKeys.fcmToken, token);
      debugPrint('FCM token: $token');
    }

    _messaging.onTokenRefresh.listen((newToken) async {
      await _storage.writeSecure(StorageKeys.fcmToken, newToken);
    });
  }

  void _listenForeground() {
    FirebaseMessaging.onMessage.listen((message) {
      final notification = message.notification;
      if (notification != null) {
        _showLocalNotification(
          id: message.hashCode,
          title: notification.title ?? 'InvestAI',
          body: notification.body ?? '',
        );
      }
    });
  }

  Future<void> _showLocalNotification({
    required int id,
    required String title,
    required String body,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'investai_channel',
      'InvestAI Notifications',
      channelDescription: 'Alertes et notifications InvestAI',
      importance: Importance.high,
      priority: Priority.high,
    );
    const iosDetails = DarwinNotificationDetails();
    const details = NotificationDetails(android: androidDetails, iOS: iosDetails);
    await _localNotifications.show(id, title, body, details);
  }

  Future<String?> getToken() async {
    return _storage.readSecure(StorageKeys.fcmToken);
  }
}
