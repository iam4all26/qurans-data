# qurans-data

Data pack for the Qur'an Studio app, built by GitHub Actions (tools/build_data.py).

Run it: Actions tab, "Build Qur'an data", Run workflow. It writes the folder `data/`:

- quran.db: 114 surahs, 6,236 verses (the build fails if the counts or numbering are wrong)
- translations/en_sahih.json and translations/ha_gumi.json
- reciters.json (each reciter folder is checked against EveryAyah)
- fonts/AmiriQuran-Regular.ttf (SIL Open Font Licence)
- catalog.json (sizes and SHA-256 checksums) and report.json (checks, warnings)

Credits and terms: Qur'an text from Tanzil (tanzil.net); Hausa translation from QuranEnc.com
(key hausa_gummi); English Sahih International via Tanzil; recordings belong to their reciters
and are never stored here.
