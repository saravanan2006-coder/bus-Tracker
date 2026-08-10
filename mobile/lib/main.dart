import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'core/api_client.dart';
import 'core/localization/localization_controller.dart';
import 'core/push/push_service.dart';
import 'core/repository/app_repository.dart';
import 'core/theme/app_theme.dart';
import 'features/driver/controllers/auth_controller.dart';
import 'features/driver/controllers/driver_controller.dart';
import 'features/public/controllers/public_controller.dart';
import 'features/public/screens/public_home_screen.dart';

/// Global messenger so pushes can surface a message on any screen.
final GlobalKey<ScaffoldMessengerState> rootMessengerKey =
    GlobalKey<ScaffoldMessengerState>();

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  if (!kIsWeb) {
    // Foreground-task isolate plumbing is Android-only (dart:isolate).
    FlutterForegroundTask.initCommunicationPort();
  }
  runApp(const BusTrackerApp());
}

class BusTrackerApp extends StatelessWidget {
  const BusTrackerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => LocalizationController()..load()),
        Provider(create: (_) => ApiClient()),
        Provider(
          create: (context) => AppRepository(context.read<ApiClient>()),
        ),
        ChangeNotifierProvider(
          create: (context) => AuthController(context.read<AppRepository>()),
        ),
        ChangeNotifierProvider(
          create: (context) => PublicController(context.read<AppRepository>()),
        ),
        ChangeNotifierProvider(
          create: (context) => DriverController(context.read<AppRepository>()),
        ),
      ],
      child: Consumer<LocalizationController>(
        builder: (context, loc, _) {
          final language = loc.language;
          return MaterialApp(
            title: 'BusTracker',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.light(),
            scaffoldMessengerKey: rootMessengerKey,
            locale: Locale(language),
            supportedLocales: const [Locale('ta'), Locale('en')],
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            home: const RootGate(),
          );
        },
      ),
    );
  }
}

/// Always opens on the passenger app. If a driver session exists it is
/// silently restored so the driver can jump straight to their buses.
class RootGate extends StatefulWidget {
  const RootGate({super.key});

  @override
  State<RootGate> createState() => _RootGateState();
}

class _RootGateState extends State<RootGate> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthController>().restoreSession();
      // Surface push alerts as an in-app message. No-op when Firebase is
      // not configured (local demo).
      PushService.startListening(
        onMessage: _showPushMessage,
        onMessageOpened: _showPushMessage,
      );
    });
  }

  void _showPushMessage(String? title, String? body) {
    final messenger = rootMessengerKey.currentState;
    if (messenger == null) return;
    messenger.showSnackBar(
      SnackBar(content: Text(body ?? title ?? '')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return const PublicHomeScreen();
  }
}
