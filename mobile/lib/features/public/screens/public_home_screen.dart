import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/repository/app_repository.dart';
import '../../../core/storage/app_storage.dart';
import '../../driver/screens/driver_home_screen.dart';
import '../../driver/screens/login_screen.dart';
import '../controllers/public_controller.dart';import 'favorites_screen.dart';
import 'route_results_screen.dart';
import 'village_pair_screen.dart';

/// Passenger entry point: a bottom-nav shell with "Find bus" and "Favorites"
/// tabs, plus a language toggle and a link to the driver login.
class PublicHomeScreen extends StatefulWidget {
  const PublicHomeScreen({super.key});

  @override
  State<PublicHomeScreen> createState() => _PublicHomeScreenState();
}

class _PublicHomeScreenState extends State<PublicHomeScreen> {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final controller = context.read<PublicController>();
      if (controller.districts.isEmpty) await controller.loadDistricts();
      final restored = await controller.restoreDistrict();
      if (!restored) await controller.autoDetectDistrict();
      await controller.loadFavorites();
    });
  }

  Future<void> _openPair(int fromVillageId, int toVillageId) async {
    final controller = context.read<PublicController>();
    await controller.findRoutes(
      fromVillageId: fromVillageId,
      toVillageId: toVillageId,
    );
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const RouteResultsScreen()),
    );
  }

  Future<void> _openDriverMode() async {
    String? token;
    try {
      token = await AppStorage.accessToken;
    } catch (_) {
      // Secure storage is unavailable off HTTPS (e.g. plain-HTTP web demo).
      // Treat the driver as logged out.
      token = null;
    }
    if (!mounted) return;
    if (token != null) {
      final repo = context.read<AppRepository>();
      repo.setAccessToken(token);
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const DriverHomeScreen()),
      );
    } else {
      await Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();

    return Scaffold(
      appBar: AppBar(
        title: Text(loc.t('appName')),
        actions: [
          IconButton(
            icon: const Icon(Icons.translate),
            tooltip: loc.language == 'ta' ? 'English' : 'தமிழ்',
            onPressed: () => context.read<LocalizationController>().toggle(),
          ),
          IconButton(
            icon: const Icon(Icons.directions_bus),
            tooltip: loc.t('driverMode'),
            onPressed: _openDriverMode,
          ),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: [
          const VillagePairScreen(),
          FavoritesScreen(onOpenPair: _openPair),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (index) => setState(() => _tab = index),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.search),
            selectedIcon: const Icon(Icons.search),
            label: loc.t('findBuses'),
          ),
          NavigationDestination(
            icon: const Icon(Icons.star_border),
            selectedIcon: const Icon(Icons.star),
            label: loc.t('favorites'),
          ),
        ],
      ),
    );
  }
}
