# Qur'an Studio Admin (admin/index.html)

One page that edits this repo through the GitHub API, so files no longer need to be edited by hand.

Open it: download admin/index.html to the phone and open it in the browser, or turn on GitHub Pages
(Settings, Pages, branch main, folder /) and open https://iam4all26.github.io/qurans-data/admin/.
Create a fine-grained token for this repository only (Contents: Read and write, Actions: Read and write),
paste it once; it is saved only in that browser. Never commit a token.

Tabs
- App control: edits data/app_config.json (no build needed).
- Backgrounds: uploads MP4 clips with their source and licence, edits and deletes records (starts a build).
- Reciters: reciter photos (auto 300x300 JPG) and their records, and extra reciters in data/reciters_extra.json (starts a build).
- Build: starts the data workflow, shows the last runs and report.json warnings.

Not covered: templates (they live in the app, assets/templates), the RECITERS list and HIDDEN set in tools/build_data.py.
