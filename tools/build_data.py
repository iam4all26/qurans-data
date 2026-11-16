#!/usr/bin/env python3
"""Builds the Qur'an Studio data pack.

Downloads the sources, checks them (114 surahs, 6,236 verses, numbering), and writes
data/quran.db, data/translations/*.json, data/reciters.json, data/fonts/*, data/catalog.json
and data/report.json. Exits with an error when a structural check fails, so a bad
download never replaces good data.

Standard library only. Run on GitHub Actions (the phone and the chat have no network).
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

OUT = os.environ.get("OUT_DIR", "data")
UA = {"User-Agent": "QuranStudioDataBuilder/0.1 (+https://github.com/Iam4all26/qurans-data)"}
TOTAL_SURAHS = 114
TOTAL_VERSES = 6236

ALQ = "https://api.alquran.cloud/v1"
QURANENC = "https://quranenc.com/api/v1"
EVERYAYAH = "https://everyayah.com/data"
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/amiriquran/AmiriQuran-Regular.ttf"
FONT_LICENCE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/amiriquran/OFL.txt"

RECITERS = [
    ("alafasy", "Mishary Rashid Alafasy", "Alafasy_128kbps"),
    ("husary", "Mahmoud Khalil Al-Husary", "Husary_128kbps"),
    ("abdulbasit_murattal", "Abdul Basit Abdus Samad (Murattal)", "Abdul_Basit_Murattal_192kbps"),
    ("muaiqly", "Maher Al Muaiqly", "MaherAlMuaiqly128kbps"),
    ("sudais", "Abdurrahman As-Sudais", "Abdurrahmaan_As-Sudais_192kbps"),
    ("ghamdi", "Saad Al-Ghamdi", "Ghamadi_40kbps"),
]

errors = []
warnings = []
checks = []


def fail(msg):
    errors.append(msg)
    print("ERROR:", msg, file=sys.stderr)


def warn(msg):
    warnings.append(msg)
    print("WARN:", msg, file=sys.stderr)


def ok(name, detail=""):
    checks.append({"check": name, "result": "ok", "detail": detail})
    print("ok:", name, detail)


def fetch(url, tries=4, method="GET"):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA, method=method)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 401, 403, 404):
                return e.code, b""
        except Exception as e:  # network trouble: retry
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("Could not fetch %s: %s" % (url, last))


def fetch_json(url):
    status, body = fetch(url)
    if status != 200:
        raise RuntimeError("HTTP %s for %s" % (status, url))
    return json.loads(body.decode("utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_STRIP = re.compile("[ً-ٰٟۖ-ۭـ࣓-ࣿ]")


def normalise(text):
    """Letters only, for comparing two editions. Never used for stored text."""
    text = _STRIP.sub("", text)
    for a in "أإآٱ":
        text = text.replace(a, "ا")
    text = text.replace("ى", "ي").replace("ی", "ي").replace("ک", "ك")
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------- Arabic text

def load_edition(edition):
    data = fetch_json("%s/quran/%s" % (ALQ, edition))["data"]
    surahs = data["surahs"]
    return surahs


def check_structure(surahs, label):
    if len(surahs) != TOTAL_SURAHS:
        fail("%s: expected %d surahs, got %d" % (label, TOTAL_SURAHS, len(surahs)))
    total = 0
    for i, s in enumerate(surahs, start=1):
        if s["number"] != i:
            fail("%s: surah order broken at %d" % (label, i))
        ayahs = s["ayahs"]
        total += len(ayahs)
        for j, a in enumerate(ayahs, start=1):
            if a["numberInSurah"] != j:
                fail("%s: numbering broken at %d:%d" % (label, i, j))
            if not str(a["text"]).strip():
                fail("%s: empty verse %d:%d" % (label, i, j))
    if total != TOTAL_VERSES:
        fail("%s: expected %d verses, got %d" % (label, TOTAL_VERSES, total))
    else:
        ok("%s structure" % label, "%d surahs, %d verses" % (len(surahs), total))


def strip_basmala_prefix(surahs):
    """Some editions glue the Basmala in front of verse 1 of each surah (except 1 and 9).
    The Basmala is stored once on its own. Only that exact prefix is removed; nothing else
    in the text is touched. Returns (basmala_text, number_stripped)."""
    # The source puts an invisible byte order mark (U+FEFF) at the start of the
    # text. It is not part of the Qur'an text and it stopped the prefix match.
    for s in surahs:
        for a in s["ayahs"]:
            a["text"] = a["text"].replace("\ufeff", "").strip()
    basmala = surahs[0]["ayahs"][0]["text"]
    words = basmala.split(" ")
    stripped = 0
    for s in surahs:
        if s["number"] in (1, 9):
            continue
        first = s["ayahs"][0]
        parts = first["text"].split(" ")
        if parts[: len(words)] == words and len(parts) > len(words):
            first["text"] = " ".join(parts[len(words):])
            stripped += 1
    if stripped not in (0, 112):
        fail("basmala: removed from %d surahs, expected 0 or 112" % stripped)
    for s in surahs:
        if s["number"] in (1, 9):
            continue
        if s["ayahs"][0]["text"].split(" ")[: len(words)] == words:
            fail("basmala still attached to the first verse of surah %d" % s["number"])
    return basmala, stripped


# ---------------------------------------------------------------- translations

def alq_translation(surahs):
    out = []
    for s in surahs:
        for a in s["ayahs"]:
            out.append(str(a["text"]).replace("\ufeff", "").strip())
    return out


def quranenc_translation(key, arabic_surahs):
    verses = []
    arabic_mismatch = 0
    for n in range(1, TOTAL_SURAHS + 1):
        res = fetch_json("%s/translation/sura/%s/%d" % (QURANENC, key, n))["result"]
        expected = len(arabic_surahs[n - 1]["ayahs"])
        if len(res) != expected:
            fail("QuranEnc %s surah %d: %d verses, Arabic edition has %d" % (key, n, len(res), expected))
        res = sorted(res, key=lambda r: int(r["aya"]))
        for r, a in zip(res, arabic_surahs[n - 1]["ayahs"]):
            verses.append(str(r["translation"]).strip())
            ar = r.get("arabic_text")
            if ar and normalise(str(ar)) != normalise(a["text"]):
                arabic_mismatch += 1
        time.sleep(0.2)
    return verses, arabic_mismatch


def quranenc_version(key):
    try:
        data = fetch_json("%s/translations/list" % QURANENC)
        items = data.get("translations", data if isinstance(data, list) else [])
        for it in items:
            if it.get("key") == key:
                return str(it.get("version", "unknown")), str(it.get("last_update", ""))
    except Exception as e:
        warn("QuranEnc version lookup failed: %s" % e)
    return "unknown (not returned by the API)", ""


# ----------------------------------------------------------------------- write

def write_db(path, surahs, basmala, sources):
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE surahs(number INTEGER PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT NOT NULL,
            name_en_translation TEXT NOT NULL, revelation_type TEXT NOT NULL, ayah_count INTEGER NOT NULL);
        CREATE TABLE verses(surah INTEGER NOT NULL, ayah INTEGER NOT NULL, text TEXT NOT NULL,
            juz INTEGER, page INTEGER, PRIMARY KEY(surah, ayah));
        CREATE TABLE sources(id TEXT PRIMARY KEY, name TEXT, type TEXT, language TEXT, version TEXT,
            url TEXT, licence TEXT, attribution TEXT, downloaded_at TEXT);
        """
    )
    for s in surahs:
        db.execute("INSERT INTO surahs VALUES (?,?,?,?,?,?)",
                   (s["number"], s["name"], s["englishName"], s["englishNameTranslation"],
                    s["revelationType"], len(s["ayahs"])))
        for a in s["ayahs"]:
            db.execute("INSERT INTO verses VALUES (?,?,?,?,?)",
                       (s["number"], a["numberInSurah"], a["text"].strip(), a.get("juz"), a.get("page")))
    db.execute("INSERT INTO meta VALUES ('basmala', ?)", (basmala,))
    db.execute("INSERT INTO meta VALUES ('surah_count', ?)", (str(len(surahs)),))
    db.execute("INSERT INTO meta VALUES ('verse_count', ?)", (str(sum(len(s['ayahs']) for s in surahs)),))
    for src in sources:
        db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                   (src["id"], src["name"], src["type"], src["language"], src["version"], src["url"],
                    src["licence"], src["attribution"], src["downloaded_at"]))
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    db.execute("VACUUM")
    db.close()
    if n != TOTAL_VERSES:
        fail("quran.db has %d verses" % n)
    else:
        ok("quran.db written", "%d verses" % n)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.join(OUT, "translations"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "fonts"), exist_ok=True)
    sources = []

    # Arabic
    arabic = load_edition("quran-uthmani")
    check_structure(arabic, "quran-uthmani")
    basmala, stripped = strip_basmala_prefix(arabic)
    ok("basmala handling", "stored once; prefix removed from %d surah openings" % stripped)
    sources.append({
        "id": "ar_uthmani", "name": "Qur'an text, Uthmani (Tanzil Madinah Mushaf text via AlQuran Cloud)",
        "type": "text", "language": "ar", "version": "alquran.cloud quran-uthmani",
        "url": "https://api.alquran.cloud/v1/quran/quran-uthmani",
        "licence": "Tanzil terms: unmodified text, credit Tanzil with a link, non-commercial use unless permitted. See https://tanzil.net/docs/faq",
        "attribution": "Qur'an text from Tanzil Project (tanzil.net)", "downloaded_at": now})

    # English
    en = load_edition("en.sahih")
    check_structure(en, "en.sahih")
    en_verses = alq_translation(en)
    if len(en_verses) != TOTAL_VERSES:
        fail("English translation has %d verses" % len(en_verses))
    en_src = {
        "id": "en_sahih", "name": "Sahih International", "type": "translation", "language": "en",
        "version": "alquran.cloud en.sahih", "url": "https://api.alquran.cloud/v1/quran/en.sahih",
        "licence": "Tanzil translation terms: unmodified, credit the source. Not guaranteed authentic by Tanzil.",
        "attribution": "English translation: Sahih International, via Tanzil / AlQuran Cloud", "downloaded_at": now}
    sources.append(en_src)
    write_json(os.path.join(OUT, "translations", "en_sahih.json"), {
        "id": "en_sahih", "language": "en", "direction": "ltr", "name": "Sahih International",
        "translator": "Sahih International", "source": en_src["url"], "version": en_src["version"],
        "attribution": en_src["attribution"], "licence": en_src["licence"], "downloaded_at": now,
        "order": "surah, then verse (6236 entries)", "count": len(en_verses), "verses": en_verses})

    # Hausa (QuranEnc, with AlQuran Cloud as fallback)
    ha_key = "hausa_gummi"
    ha_verses, mism, ha_source, ha_ver, ha_date = None, 0, None, "", ""
    try:
        ha_verses, mism = quranenc_translation(ha_key, arabic)
        ha_ver, ha_date = quranenc_version(ha_key)
        ha_source = "https://quranenc.com/en/browse/%s" % ha_key
        ok("QuranEnc Hausa", "%d verses, Arabic text differs (letters only) in %d verses" % (len(ha_verses), mism))
        if mism > 62:
            warn("QuranEnc Arabic differs from the Uthmani text in %d verses; check the report" % mism)
    except Exception as e:
        warn("QuranEnc Hausa failed (%s); falling back to AlQuran Cloud ha.gumi" % e)
        ha = load_edition("ha.gumi")
        check_structure(ha, "ha.gumi")
        ha_verses = alq_translation(ha)
        ha_source = "https://api.alquran.cloud/v1/quran/ha.gumi"
        ha_ver = "alquran.cloud ha.gumi (QuranEnc unavailable)"
    if len(ha_verses) != TOTAL_VERSES:
        fail("Hausa translation has %d verses" % len(ha_verses))
    ha_src = {
        "id": "ha_gumi", "name": "Hausa translation, Abu Bakr Mahmoud Gumi (QuranEnc key hausa_gummi)",
        "type": "translation", "language": "ha", "version": ha_ver, "url": ha_source,
        "licence": "QuranEnc terms: do not modify, add or delete; credit QuranEnc.com as source; show the version number; keep transcript info; update to the latest version; no inappropriate ads. See https://quranenc.com",
        "attribution": "Hausa translation from QuranEnc.com", "downloaded_at": now}
    sources.append(ha_src)
    write_json(os.path.join(OUT, "translations", "ha_gumi.json"), {
        "id": "ha_gumi", "language": "ha", "direction": "ltr", "name": "Hausa (Gumi)",
        "translator": "Abu Bakr Mahmoud Gumi", "source": ha_source, "version": ha_ver,
        "last_update": ha_date, "attribution": ha_src["attribution"], "licence": ha_src["licence"],
        "downloaded_at": now, "order": "surah, then verse (6236 entries)", "count": len(ha_verses),
        "verses": ha_verses})

    # Database
    write_db(os.path.join(OUT, "quran.db"), arabic, basmala, sources)

    # Reciters (checked against EveryAyah)
    reciters = []
    for rid, name, folder in RECITERS:
        url = "%s/%s/001001.mp3" % (EVERYAYAH, folder)
        try:
            status, _ = fetch(url, tries=2)
        except Exception as e:
            status = "error: %s" % e
        verified = status == 200
        if not verified:
            warn("Reciter %s folder %s not confirmed (%s)" % (rid, folder, status))
        reciters.append({
            "id": rid, "name": name, "folder": folder,
            "per_ayah_url": "%s/%s/{SSS}{AAA}.mp3" % (EVERYAYAH, folder),
            "verified": verified, "check_status": str(status), "checked_at": now,
            "timing": None,
            "licence": "Recordings belong to the reciter. Not bundled; downloaded on the user's phone. Credit the reciter."})
    write_json(os.path.join(OUT, "reciters.json"), {"version": 1, "reciters": reciters})
    ok("reciters", "%d of %d confirmed" % (sum(1 for r in reciters if r["verified"]), len(reciters)))

    # Font
    font_entries = []
    try:
        st, body = fetch(FONT_URL)
        st2, lic = fetch(FONT_LICENCE_URL)
        if st == 200 and len(body) > 10000:
            with open(os.path.join(OUT, "fonts", "AmiriQuran-Regular.ttf"), "wb") as f:
                f.write(body)
            if st2 == 200:
                with open(os.path.join(OUT, "fonts", "AmiriQuran-OFL.txt"), "wb") as f:
                    f.write(lic)
            font_entries.append("fonts/AmiriQuran-Regular.ttf")
            ok("font", "Amiri Quran (SIL Open Font Licence)")
        else:
            warn("Amiri Quran download failed (HTTP %s)" % st)
    except Exception as e:
        warn("Amiri Quran download failed: %s" % e)

    # Catalogue with checksums
    files = []
    def add(rel, kind, extra=None):
        p = os.path.join(OUT, rel)
        entry = {"id": os.path.splitext(os.path.basename(rel))[0], "type": kind, "path": rel,
                 "sizeBytes": os.path.getsize(p), "sha256": sha256(p)}
        if extra:
            entry.update(extra)
        files.append(entry)
    add("quran.db", "database", {"verses": TOTAL_VERSES, "surahs": TOTAL_SURAHS})
    add("translations/en_sahih.json", "translation", {"language": "en"})
    add("translations/ha_gumi.json", "translation", {"language": "ha"})
    add("reciters.json", "reciters")
    for rel in font_entries:
        add(rel, "font", {"family": "Amiri Quran"})
    write_json(os.path.join(OUT, "catalog.json"), {"version": 1, "built_at": now, "files": files})
    write_json(os.path.join(OUT, "report.json"), {
        "built_at": now, "ok": not errors, "errors": errors, "warnings": warnings, "checks": checks,
        "basmala_prefix_removed_from": stripped, "quranenc_arabic_letter_differences": mism})

    print("\nDone. errors=%d warnings=%d" % (len(errors), len(warnings)))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
