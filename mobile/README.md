# BusTracker mobile

Flutter client for BusTracker — driver and public experiences in one codebase.

- `lib/features/driver/` — OTP login, bus registration, route build, live trip sharing
- `lib/features/public/` — district → village navigation, live map, ETA, favorites, alerts
- `lib/core/` — models, repository, WebSocket client, localization, geo helpers

```bash
flutter pub get
flutter analyze      # must be clean
flutter test         # unit tests (geo formatting, JSON models)
flutter build apk --debug   # requires the Android SDK
```

Point the API base URL at your backend in `lib/core/config.dart`. See the
project root `README.md` for architecture and deployment.
