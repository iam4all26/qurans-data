# Controlling Qur'an Studio from this repo

Edit `data/app_config.json` in K-Git Studio and commit. The app reads it when it starts and when
it comes back to the front (at most every 6 hours; "Try again" on a blocking screen reads it at once).
GitHub may keep the old copy for about 5 minutes. The app downloads this file only; it sends nothing
about the user. Offline, the app keeps using the last copy it read.

Versions are the version names you give the app, such as 1.0.0 or 1.1.0 (the part before the + in
pubspec.yaml: `version: 1.1.0+7` is version 1.1.0). Always put the new version in pubspec.yaml before a
release; the number after the + must still be bigger than the last release for the Play Store.

| Field | What it does |
|---|---|
| `min_version` | Phones with an older version (for example 1.0.0 when this is 1.1.0) see "Update required" and cannot use the app until they update. Empty = off. |
| `latest_version` | Phones with an older version see a "new version" bar with Update and Later (Later hides it for that version). Empty = off. |
| `update_message` | Text for both screens. Empty = a default text. |
| `play_url` | Leave empty to use the Play Store page of the app (package id read from the app). Set it only to use another link. |
| `announcement` | `id` must change for every new message (any text, for example "ramadan-1"). Each phone shows it once. Empty id = no message. |
| `maintenance.on` | true shows "Back soon" with `text` and blocks the app. |
| `disabled.all` | true blocks the whole app with `all_text`. |
| `disabled.features` | List of switches. Supported now: `"export"`. The message is `feature_text`. |

## Examples

Force everyone below 1.1.0 to update:
`"min_version": "1.1.0", "latest_version": "1.1.0", "update_message": "Please update to continue."`

Suggest an update without forcing it: `"min_version": "", "latest_version": "1.1.0"`.

Turn off export for a problem: `"disabled": { "all": false, "all_text": "", "features": ["export"], "feature_text": "Export is paused while we fix a problem." }`.

## Before the first Play release
Leave everything as it is (all off). After the app is published and the Play page works:
set `latest_version` to the new version for a soft notice, or `min_version` to force it.

## Limits
Only versions that contain this feature can be controlled. The control file is public (like the rest of
this repo), so do not put secrets in it. It is not a licence system.
