import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../core/localization/localization_controller.dart';
import '../../../core/models/models.dart';
import '../../../shared_widgets/loading_indicator.dart';
import '../controllers/public_controller.dart';
import 'district_select_screen.dart';
import 'route_results_screen.dart';

/// Step 2: choose "from village -> to village", then find buses.
class VillagePairScreen extends StatelessWidget {
  const VillagePairScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    final controller = context.watch<PublicController>();
    final district = controller.selectedDistrict;

    return Scaffold(
      appBar: AppBar(
        title: Text(loc.t('findBuses')),
        actions: [
          IconButton(
            tooltip: loc.t('pickDistrict'),
            icon: const Icon(Icons.location_city),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => DistrictSelectScreen(
                  onSelected: (_) => Navigator.of(context).pop(),
                ),
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: district == null
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.map_outlined, size: 56),
                      const SizedBox(height: 12),
                      Text(loc.t('pickDistrict')),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => DistrictSelectScreen(
                              onSelected: (_) => Navigator.of(context).pop(),
                            ),
                          ),
                        ),
                        child: Text(loc.t('selectDistrict')),
                      ),
                    ],
                  ),
                ),
              )
            : _PairForm(district: district),
      ),
    );
  }
}

class _PairForm extends StatefulWidget {
  const _PairForm({required this.district});

  final District district;

  @override
  State<_PairForm> createState() => _PairFormState();
}

class _PairFormState extends State<_PairForm> {
  Village? _from;
  Village? _to;

  Future<void> _pick(bool isFrom) async {
    final loc = context.read<LocalizationController>();
    final controller = context.read<PublicController>();
    if (controller.villages.isEmpty) await controller.loadVillages();
    if (!mounted) return;
    final picked = await showModalBottomSheet<Village>(
      context: context,
      isScrollControlled: true,
      builder: (_) => VillagePickerSheet(
        title: isFrom ? loc.t('chooseFrom') : loc.t('chooseTo'),
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

  void _swap() {
    setState(() {
      final tmp = _from;
      _from = _to;
      _to = tmp;
    });
  }

  Future<void> _submit() async {
    final controller = context.read<PublicController>();
    if (_from == null || _to == null) return;
    await controller.findRoutes(
      fromVillageId: _from!.id,
      toVillageId: _to!.id,
    );
    if (!mounted) return;
    if (controller.error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(controller.error!)),
      );
      return;
    }
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const RouteResultsScreen()),
    );
  }

  String _label(Village? village, String fallback) {
    if (village == null) return fallback;
    final loc = context.watch<LocalizationController>();
    return loc.language == 'ta' && village.nameTa != null
        ? village.nameTa!
        : village.name;
  }

  @override
  Widget build(BuildContext context) {
    final loc = context.watch<LocalizationController>();
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                children: [
                  Icon(Icons.location_city,
                      color: Theme.of(context).colorScheme.primary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      loc.language == 'ta' && widget.district.nameTa != null
                          ? widget.district.nameTa!
                          : widget.district.name,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _VillageField(
                  icon: Icons.trip_origin,
                  label: _label(_from, loc.t('chooseFrom')),
                  onTap: () => _pick(true),
                ),
              ),
              IconButton(
                onPressed: _swap,
                icon: const Icon(Icons.swap_horiz),
                tooltip: loc.t('swap'),
              ),
              Expanded(
                child: _VillageField(
                  icon: Icons.sports_score,
                  label: _label(_to, loc.t('chooseTo')),
                  onTap: () => _pick(false),
                ),
              ),
            ],
          ),
          const Spacer(),
          FilledButton.icon(
            onPressed: _from != null && _to != null ? _submit : null,
            icon: const Icon(Icons.directions_bus),
            label: Text(loc.t('findBuses')),
          ),
          const SizedBox(height: 16),
        ],
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
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        height: 72,
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

/// Modal search + list of villages for one end of the pair.
class VillagePickerSheet extends StatefulWidget {
  const VillagePickerSheet({super.key, required this.title});

  final String title;

  @override
  State<VillagePickerSheet> createState() => _VillagePickerSheetState();
}

class _VillagePickerSheetState extends State<VillagePickerSheet> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    context.read<PublicController>().loadVillages(query: value);
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
            onChanged: _onQueryChanged,
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
