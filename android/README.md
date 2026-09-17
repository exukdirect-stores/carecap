# CareCap on Google Play

CareCap is a web app (FastAPI + a single self-contained HTML page). The Play
Store listing is a thin **WebView wrapper** in this folder — it ships the
door, not the house. All logic (dose engine, digests, multi-family auth)
stays server-side, so the app updates without a Play release.

```
android/
  build.gradle            AGP 8.5.2 / Kotlin 1.9.24
  settings.gradle         :app module
  gradle/wrapper/         real wrapper (v8.9) — ./gradlew works out of the box
  app/build.gradle        minSdk 24, targetSdk 35, versionCode 1, upload signing
  app/src/main/
    AndroidManifest.xml   INTERNET only; single activity
    java/…/MainActivity.kt  WebView + DOM storage (token) + in-app back
    res/                  theme (brand teal), layout, mipmaps (icon done)
  carecap-upload.jks      the upload keystore (generated, chmod 600)
  keystore.properties     its passwords (chmod 600, git-ignored)
```

## 1) Decide the backend URL (do this first)

`app/build.gradle` → `BASE_URL` currently points at the sandbox preview,
which is **ephemeral**. Before any release:

1. Deploy the backend permanently: Render blueprint (`render.yaml`) or
   Fly (`fly.toml`) — see the main README's Publish section.
2. Put that URL in `BASE_URL` and bump `versionCode`.

## 2) One-time Play Console setup (you, ~30 min)

1. <https://play.google.com/console> → accept the developer agreement
   (one-time **$25** fee, identity verification).
2. **Create app** → name "CareCap", English (US), app, free.
3. **Store presence → Store presence → Content** → fill the listing:
   - Short description: *"Your parent's meds, refills, money, and the weekly
     family digest — in one quiet app."*
   - Full description, screenshots (phone), feature graphic (use
     `assets/icon-512-square.png` as a base).
4. **Release → Signing** → choose **Play App Signing** (Google holds the
   master key; you hand over the upload key — the one already generated
   here).
5. App content → privacy policy URL (publish a page; the app stores no
   personal data on-device beyond the family token in localStorage).
6. App content → content rating questionnaire (~10 min, "Everyone" likely).

## 3) Upload the first build

**Option A — CI (recommended):** push to GitHub with the workflow in
`../.github/workflows/android.yml`, add these repo secrets:

| Secret | Value |
|---|---|
| `CARECAP_KEYSTORE_BASE64` | `base64 android/carecap-upload.jks` |
| `CARECAP_KEYSTORE_PASSWORD` | from `keystore.properties` |
| `CARECAP_KEY_ALIAS` | `carecap-upload` |
| `CARECAP_KEY_PASSWORD` | from `keystore.properties` |

Tag `v0.5.0` (or run the workflow) → download artifact
`carecap-release/app-release.aab` → Play Console → **Production → Create
new release → upload the .aab** → first upload auto-registers the upload
key → expand to a **closed testing track** (your family group) → submit.

**Option B — local:** with Android Studio (or JDK 17 + Android SDK 35):

```bash
cd android
./gradlew bundleRelease
# → app/build/outputs/bundle/release/app-release.aab
```

## 4) What the store version actually is

- Launches the deployed CareCap URL in a full WebView (JS + localStorage
  enabled, so the captain's token sign-in works unchanged).
- The PWA manifest + service worker inside the web app keep it
  installable/updatable independently of the store.
- Every backend deploy (new features, fixes) is instantly live for all
  store users — no review wait.

## Release checklist

- [ ] `BASE_URL` points at the permanent backend
- [ ] `versionCode` bumped (+1 per upload — mandatory)
- [ ] Keystore = the registered upload key
- [ ] AAB signed (`bundleRelease` with `keystore.properties` present)
- [ ] New screenshots if the UI changed
- [ ] Phased rollout (10% → 100%) for anything beyond trivial
