import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../core/repository/app_repository.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../../public/controllers/public_controller.dart';

/// Driver flow: pick district + start/end villages, build (or reuse) a route,
/// then assign it to one of the driver's buses.
class BuildRouteScreen extends StatefulWidget {
  const BuildRouteScreen({super.key, required this.buses});

  final List<Bus> buses;

  @override
  State<BuildRouteScreen> createState() => _BuildRouteScreenState();
}

class _BuildRouteScreenState extends State<BuildRouteScreen> {
  District? _district;
  Village? _from;
  Village? _to;
  bool _building = false;
  String? _error;

  Future<void> _pickDistrict() async {
    final controller = context.read<PublicController>();
    if (controller.districts.isEmpty) await controller.loadDistricts();
    if (!mounted) return;
    final picked = await showModalBottomSheet<District>(
      context: context,
      builder: (_) => _DistrictSheet(),
    );
    if (picked != null) {
      setState(() {
        _district = picked;
        _from = null;
        _to = null;
      });
      controller.selectDistrict(picked);
    }
  }

  Future<void> _pickVillage(bool isFrom) async {
    final controller = context.read<PublicController>();
    final loc = context.read<LocalizationController>();
    if (_district == null) return;
    if (controller.villages.isEmpty) await controller.loadVillages();
    if (!mounted) return;
    final picked = await showModalBottomSheet<Village>(
      context: context,
      builder: (_) => _VillageSheet(
        title: isFrom ? loc.t('chooseRouteFrom') : loc.t('chooseRouteTo'),
      ),
    );
    if (picked != null) {
      setState(() {
        if (isFrom) {
          _from = picked;
          if (_to?.id == _from?.id) _to = null;
        } else {
          _to = picked;
          if (_from?.id == _to?.id) _from = null;
        }
      });
    }
  }

  Future<void> _buildAndAssign() async {
    final loc = context.read<LocalizationController>();
    final repo = context.read<AppRepository>();
    final district = _district;
    final from = _from;
    final to = _to;
    if (district == null || from == null || to == null) return;

    setState(() {
      _building = true;
      _error = null;
    });
    try {
      final route = await repo.buildRoute(
        districtId: district.id,
        fromVillageId: from.id,
        toVillageId: to.id,
      );
      if (!mounted) return;
      setState(() => _building = false);

      final bus = await _pickBus();
      if (bus == null) return;
      await repo.assignRoute(busId: bus.id, routeId: route.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(loc.t('routeAssigned'))),
      );
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _building = false;
        _error = loc.t('routeFailed');
      });
    }
  }

  Future<Bus?> _pickBus() async {
    final loc = context.read<LocalizationController>();
    if (widget.buses.isEmpty) return null;
    return showModalBottomSheet<Bus>(
      context: context,
      builder: (_) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(loc.t('assignBus'),
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w700)),
            ),
            for (final bus in widget.buses)
              ListTile(
                leading: const Icon(Icons.directions_bus),
                title: Text(bus.busNumber),
                subtitle: Text(bus.verificationStatus),
                onTap: () => Navigator.of(context).pop(bus),
              ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final canBuild = _district != null && _from != null && _to != null;

    return Scaffold(
      appBar: AppBar(title: Text(loc.t('buildRoute'))),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Card(
                child: ListTile(
                  leading: const Icon(Icons.location_city),
                  title: Text(_district?.name ?? loc.t('pickRouteDistrict')),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _pickDistrict,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: _VillageField(
                      icon: Icons.trip_origin,
                      label: _from?.name ?? loc.t('chooseRouteFrom'),
                      onTap: _district == null ? null : () => _pickVillage(true),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _VillageField(
                      icon: Icons.sports_score,
                      label: _to?.name ?? loc.t('chooseRouteTo'),
                      onTap: _district == null ? null : () => _pickVillage(false),
                    ),
                  ),
                ],
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    _error!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              const Spacer(),
              FilledButton.icon(
                onPressed: canBuild && !_building ? _buildAndAssign : null,
                icon: _building
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.route),
                label: Text(
                  _building ? loc.t('routeBuilding') : loc.t('buildRoute'),
                ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}

class _VillageField extends StatelessWidget {
  const _VillageField({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        height: 76,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            const SizedBox(height: 6),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }
}

class _DistrictSheet extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();
    return SafeArea(
      child: SizedBox(
        height: 480,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(loc.t('pickRouteDistrict'),
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w700)),
            ),
            Expanded(
              child: controller.loadingDistricts
                  ? const LoadingIndicator()
                  : ListView.builder(
                      itemCount: controller.districts.length,
                      itemBuilder: (context, index) {
                        final district = controller.districts[index];
                        return ListTile(
                          leading: const Icon(Icons.location_city),
                          title: Text(
                            loc.language == 'ta' && district.nameTa != null
                                ? district.nameTa!
                                : district.name,
                          ),
                          onTap: () => Navigator.of(context).pop(district),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _VillageSheet extends StatefulWidget {
  const _VillageSheet({required this.title});

  final String title;

  @override
  State<_VillageSheet> createState() => _VillageSheetState();
}

class _VillageSheetState extends State<_VillageSheet> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();

    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.title,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          TextField(
            controller: _searchController,
            autofocus: true,
            onChanged: (value) => controller.loadVillages(query: value),
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search),
              hintText: loc.t('searchVillages'),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 320,
            child: controller.loadingVillages
                ? const LoadingIndicator()
                : controller.villages.isEmpty
                    ? Center(child: Text(loc.t('noResults')))
                    : ListView.builder(
                        itemCount: controller.villages.length,
                        itemBuilder: (context, index) {
                          final village = controller.villages[index];
                          final name = loc.language == 'ta' &&
                                  village.nameTa != null
                              ? village.nameTa!
                              : village.name;
                          return ListTile(
                            leading: const Icon(Icons.place_outlined),
                            title: Text(name),
                            onTap: () => Navigator.of(context).pop(village),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
