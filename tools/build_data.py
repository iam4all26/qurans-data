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
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
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
    # More EveryAyah folders. Each one is tested with 001001.mp3; a folder that does not answer
    # HTTP 200 is NOT published and the app never shows it (see report.json warnings).
    ("shuraym", "Saud Ash-Shuraym", "Saood_ash-Shuraym_128kbps"),
    ("shatree", "Abu Bakr Ash-Shatri", "Abu_Bakr_Ash-Shaatree_128kbps"),
    ("rifai", "Hani Ar-Rifai", "Hani_Rifai_192kbps"),
    ("hudhaify", "Ali Al-Hudhaify", "Hudhaify_128kbps"),
    ("minshawy_murattal", "Mohamed Siddiq Al-Minshawi (Murattal)", "Minshawy_Murattal_128kbps"),
    ("minshawy_mujawwad", "Mohamed Siddiq Al-Minshawi (Mujawwad)", "Minshawy_Mujawwad_192kbps"),
    ("husary_muallim", "Mahmoud Khalil Al-Husary (Muallim)", "Husary_Muallim_128kbps"),
    ("husary_mujawwad", "Mahmoud Khalil Al-Husary (Mujawwad)", "Husary_Mujawwad_128kbps"),
    ("abdulbasit_mujawwad", "Abdul Basit Abdus Samad (Mujawwad)", "Abdul_Basit_Mujawwad_128kbps"),
    ("ajamy", "Ahmed Al-Ajmi", "Ahmed_ibn_Ali_al-Ajamy_128kbps_ketaballah.net"),
    ("basfar", "Abdullah Basfar", "Abdullah_Basfar_192kbps"),
    ("matroud", "Abdullah Matroud", "Abdullah_Matroud_128kbps"),
    ("budair", "Salah Al-Budair", "Salah_Al_Budair_128kbps"),
    ("bukhatir", "Salah Bukhatir", "Salaah_AbdulRahman_Bukhatir_128kbps"),
    ("qatami", "Nasser Al-Qatami", "Nasser_Alqatami_128kbps"),
    ("dussary", "Yasser Ad-Dosari", "Yasser_Ad-Dussary_128kbps"),
    ("ayyoub", "Muhammad Ayyub", "Muhammad_Ayyoub_128kbps"),
    ("jibreel", "Muhammad Jibreel", "Muhammad_Jibreel_128kbps"),
    ("ali_jaber", "Ali Jaber", "Ali_Jaber_64kbps"),
    ("fares_abbad", "Fares Abbad", "Fares_Abbad_64kbps"),
    ("tunaiji", "Khalifa At-Tunaiji", "Khalefa_Al_Tunaiji_64kbps"),
    ("akhdar", "Ibrahim Al-Akhdar", "Ibrahim_Akhdar_32kbps"),
    ("mustafa_ismail", "Mustafa Ismail", "Mustafa_Ismail_48kbps"),
    ("ayman_sowaid", "Ayman Sowaid", "Ayman_Sowaid_64kbps"),
    ("alafasy_64", "Mishary Rashid Alafasy (64 kbps, smaller files)", "Alafasy_64kbps"),
    ("juhani", "Abdullah Awad Al-Juhani", "Abdullaah_3awwaad_Al-Juhaynee_128kbps"),
]

# Other folder spellings to try when the first one does not answer HTTP 200 (first hit wins).
FOLDER_ALTERNATIVES = {
    "juhani": ["Abdullaah_3awwaad_Al-Juhaynee_128kbps", "Abdullah_Awad_Al-Juhani_128kbps",
               "Abdullaah_Awwaad_Al-Juhaynee_128kbps", "Abdullah_Al-Juhani_128kbps"],
}

COUNTRY = {
    "alafasy": "Kuwait", "alafasy_64": "Kuwait", "husary": "Egypt", "husary_muallim": "Egypt",
    "husary_mujawwad": "Egypt", "abdulbasit_murattal": "Egypt", "abdulbasit_mujawwad": "Egypt",
    "minshawy_murattal": "Egypt", "minshawy_mujawwad": "Egypt", "mustafa_ismail": "Egypt",
    "muaiqly": "Saudi Arabia", "sudais": "Saudi Arabia", "ghamdi": "Saudi Arabia",
    "shuraym": "Saudi Arabia", "shatree": "Saudi Arabia", "hudhaify": "Saudi Arabia",
    "basfar": "Saudi Arabia", "budair": "Saudi Arabia", "qatami": "Kuwait", "dussary": "Saudi Arabia",
    "ayyoub": "Saudi Arabia", "juhani": "Saudi Arabia", "ajamy": "Kuwait", "rifai": "Lebanon",
    "matroud": "Saudi Arabia", "bukhatir": "UAE", "tunaiji": "UAE", "jibreel": "Egypt",
    "ali_jaber": "Saudi Arabia", "fares_abbad": "Yemen", "akhdar": "Saudi Arabia",
    "ayman_sowaid": "Saudi Arabia",
}

PICTURE_MAX_BYTES = 400 * 1024

# Reciters from other sources (for example Nigerian reciters), written by hand in
# data/reciters_extra.json. Each entry needs: id, name, country, per_ayah_url with {SSS}{AAA}
# (surah and verse as three digits each, same as EveryAyah), and source, licence, attribution.
# The first verse (001001) is tested, and an entry without source and licence is NOT published.
EXTRA_RECITERS_FILE = "reciters_extra.json"

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


_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def _nw(word):
    """A word with invisible characters, marks and letter variants removed. Used only to
    compare; the stored text is never normalised."""
    return normalise(_INVISIBLE.sub("", word))


def _codepoints(text, n=40):
    return " ".join("U+%04X" % ord(c) for c in text[:n])


def strip_basmala_prefix(surahs):
    """Some editions glue the Basmala in front of verse 1 of each surah (except 1 and 9).
    The Basmala is stored once on its own and removed from verse 1. Only the Basmala words
    are removed; nothing else in the text is touched. Returns (basmala_text, number_stripped).

    Words are compared without marks, so a spelling variant of the same Basmala still
    matches. The build fails only if a Basmala is still attached after stripping."""
    # The source puts an invisible byte order mark (U+FEFF) at the start of the
    # text. It is not part of the Qur'an text and it stopped the prefix match.
    for s in surahs:
        for a in s["ayahs"]:
            a["text"] = _INVISIBLE.sub("", a["text"]).strip()
    basmala = surahs[0]["ayahs"][0]["text"]
    words = basmala.split(" ")
    wn = [_nw(w) for w in words]
    stripped = 0
    unmatched = []
    for s in surahs:
        if s["number"] in (1, 9):
            continue
        first = s["ayahs"][0]
        parts = first["text"].split(" ")
        head = [_nw(w) for w in parts[: len(words)]]
        if head == wn and len(parts) > len(words):
            first["text"] = " ".join(parts[len(words):])
            stripped += 1
        elif (len(parts) >= len(words) and head[:-1] == wn[:-1] and head[-1].startswith(wn[-1])
              and len(head[-1]) > len(wn[-1]) and parts[len(words) - 1].startswith(words[-1])):
            # Basmala glued to the next word without a space.
            rest = parts[len(words) - 1][len(words[-1]):]
            first["text"] = " ".join([rest] + parts[len(words):])
            stripped += 1
        else:
            unmatched.append(s["number"])
    if stripped not in (0, 112):
        warn("basmala: removed from %d surahs (112 expected); not matched: %s" % (stripped, unmatched))
        for n in unmatched[:5]:
            warn("surah %d verse 1 starts with: %s" % (n, _codepoints(surahs[n - 1]["ayahs"][0]["text"])))
    for s in surahs:
        if s["number"] in (1, 9):
            continue
        t = s["ayahs"][0]["text"].split(" ")
        if t and _nw(t[0]) == wn[0]:
            fail("basmala still attached to the first verse of surah %d: %s" % (s["number"], _codepoints(s["ayahs"][0]["text"])))
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


def probe_video(path):
    """Duration (ms), width, height and whether it has sound, read with ffprobe."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", path], capture_output=True, text=True, timeout=60, check=True).stdout
        j = json.loads(out)
        dur = int(float(j.get("format", {}).get("duration", 0)) * 1000)
        w = h = 0
        audio = False
        for st in j.get("streams", []):
            if st.get("codec_type") == "video" and not w:
                w, h = int(st.get("width", 0)), int(st.get("height", 0))
            if st.get("codec_type") == "audio":
                audio = True
        return dur, w, h, audio
    except Exception as e:
        warn("ffprobe failed for %s: %s" % (path, e))
        return None


def attach_pictures(reciters):
    """Adds image, image_licence and image_attribution to a reciter when data/reciters/<id>.jpg|png|webp
    exists, is at most 400 KB and has an entry with source and licence in data/reciters/images.json."""
    folder = os.path.join(OUT, "reciters")
    meta = {}
    mp = os.path.join(folder, "images.json")
    if os.path.exists(mp):
        try:
            meta = json.load(open(mp, encoding="utf-8"))
        except Exception as e:
            warn("reciters/images.json could not be read: %s" % e)
    shown = 0
    for r in reciters:
        for ext in ("jpg", "png", "webp"):
            rel = "reciters/%s.%s" % (r["id"], ext)
            path = os.path.join(OUT, rel)
            if not os.path.exists(path):
                continue
            m = meta.get(r["id"]) or {}
            if os.path.getsize(path) > PICTURE_MAX_BYTES:
                warn("Picture %s is over 400 KB: not published" % rel)
            elif not m.get("source") or not m.get("licence"):
                warn("Picture %s has no source and licence in images.json: not published" % rel)
            else:
                r["image"] = rel
                r["image_licence"] = str(m["licence"])
                r["image_attribution"] = str(m.get("attribution", ""))
                shown += 1
            break
    ok("reciter pictures", "%d of %d reciters have a published picture" % (shown, len(reciters)))


def build_backgrounds():
    """Video backgrounds: data/backgrounds/<id>.mp4 plus data/backgrounds/clips.json.

    clips.json maps each id to {"name", "category", "source", "licence", "attribution"}.
    A clip without source and licence recorded is NOT published. Writes data/backgrounds.json."""
    bdir = os.path.join(OUT, "backgrounds")
    meta = {}
    meta_path = os.path.join(bdir, "clips.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            fail("backgrounds/clips.json is not valid JSON: %s" % e)
    clips = []
    if os.path.isdir(bdir):
        for fn in sorted(os.listdir(bdir)):
            if not fn.lower().endswith(".mp4"):
                continue
            cid = fn[:-4]
            path = os.path.join(bdir, fn)
            m = meta.get(cid) or {}
            if not m.get("source") or not m.get("licence"):
                warn("Background %s skipped: record source and licence in backgrounds/clips.json" % cid)
                continue
            info = probe_video(path)
            dur, w, h, audio = info if info else (0, 0, 0, False)
            size = os.path.getsize(path)
            if info:
                if dur < 8000 or dur > 40000:
                    warn("Background %s lasts %.1f s (8 to 40 s advised)" % (cid, dur / 1000))
                if max(w, h) > 1280:
                    warn("Background %s is %dx%d (1280 on the long side advised)" % (cid, w, h))
                if audio:
                    warn("Background %s has a sound track (the app mutes it)" % cid)
            if size > 15 * 1024 * 1024:
                warn("Background %s is %.1f MB (under 15 MB advised)" % (cid, size / 1048576))
            preview = os.path.join(bdir, cid + ".jpg")
            if not os.path.exists(preview) and shutil.which("ffmpeg"):
                try:
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", path, "-frames:v", "1",
                                    "-vf", "scale=320:-2", preview], timeout=60, check=True)
                except Exception as e:
                    warn("Preview for %s failed: %s" % (cid, e))
            clips.append({
                "id": cid, "name": m.get("name", cid), "category": m.get("category", "Other"),
                "path": "backgrounds/" + fn,
                "preview": ("backgrounds/" + cid + ".jpg") if os.path.exists(preview) else "",
                "sizeBytes": size, "sha256": sha256(path), "durationMs": dur, "width": w, "height": h,
                "source": m.get("source", ""), "licence": m.get("licence", ""),
                "attribution": m.get("attribution", "")})
    write_json(os.path.join(OUT, "backgrounds.json"), {"version": 1, "clips": clips})
    ok("backgrounds", "%d clips published" % len(clips))


# More Qur'an and translation fonts from the google/fonts repository (SIL Open Font Licence).
# (folder, family, output name, candidate file names; the first one that downloads is used)
GOOGLE_FONTS = [
    ("notonaskharabic", "Noto Naskh Arabic", "NotoNaskhArabic-Regular",
     ["NotoNaskhArabic[wght].ttf", "NotoNaskhArabic-Regular.ttf"]),
    ("scheherazadenew", "Scheherazade New", "ScheherazadeNew-Regular",
     ["ScheherazadeNew-Regular.ttf"]),
    ("notokufiarabic", "Noto Kufi Arabic", "NotoKufiArabic-Regular",
     ["NotoKufiArabic[wght].ttf", "NotoKufiArabic-Regular.ttf"]),
    ("reemkufi", "Reem Kufi", "ReemKufi-Regular",
     ["ReemKufi[wght].ttf", "ReemKufi-Regular.ttf"]),
    ("notosans", "Noto Sans", "NotoSans-Regular",
     ["NotoSans[wdth,wght].ttf", "NotoSans-Regular.ttf"]),
    ("notoserif", "Noto Serif", "NotoSerif-Regular",
     ["NotoSerif[wdth,wght].ttf", "NotoSerif-Regular.ttf"]),
]


def build_google_fonts():
    done = []
    base = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    for folder, family, out_name, candidates in GOOGLE_FONTS:
        got = None
        for fname in candidates:
            try:
                st, body = fetch(base + folder + "/" + urllib.parse.quote(fname, safe=""))
            except Exception as e:
                warn("%s: %s" % (family, e))
                continue
            # A real font file starts with 0x00010000 (TrueType) or 'OTTO'.
            if st == 200 and len(body) > 20000 and body[:4] in (b"\x00\x01\x00\x00", b"OTTO"):
                got = (fname, body)
                break
        if not got:
            warn("%s could not be downloaded; templates that use it fall back to Amiri Quran" % family)
            continue
        with open(os.path.join(OUT, "fonts", out_name + ".ttf"), "wb") as f:
            f.write(got[1])
        try:
            st, lic = fetch(base + folder + "/OFL.txt")
            if st == 200:
                with open(os.path.join(OUT, "fonts", out_name + "-OFL.txt"), "wb") as f:
                    f.write(lic)
            else:
                warn("%s: licence file not found (HTTP %s)" % (family, st))
        except Exception as e:
            warn("%s licence: %s" % (family, e))
        ok("font", "%s (%s, %d KB)" % (family, got[0], len(got[1]) // 1024))
        done.append(("fonts/" + out_name + ".ttf", family))
    return done


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
        status = None
        for cand in FOLDER_ALTERNATIVES.get(rid, [folder]):
            url = "%s/%s/001001.mp3" % (EVERYAYAH, cand)
            try:
                status, _ = fetch(url, tries=2)
            except Exception as e:
                status = "error: %s" % e
            if status == 200:
                folder = cand
                break
        verified = status == 200
        if not verified:
            warn("Reciter %s folder %s not confirmed (%s)" % (rid, folder, status))
        reciters.append({
            "id": rid, "name": name, "folder": folder, "country": COUNTRY.get(rid, ""),
            "per_ayah_url": "%s/%s/{SSS}{AAA}.mp3" % (EVERYAYAH, folder),
            "verified": verified, "check_status": str(status), "checked_at": now,
            "timing": None,
            "licence": "Recordings belong to the reciter. Not bundled; downloaded on the user's phone. Credit the reciter."})
    extra_path = os.path.join(OUT, EXTRA_RECITERS_FILE)
    if os.path.exists(extra_path):
        try:
            extra = json.load(open(extra_path, encoding="utf-8")).get("reciters", [])
        except Exception as e:
            extra = []
            warn("%s could not be read: %s" % (EXTRA_RECITERS_FILE, e))
        for r in extra:
            rid, tpl = str(r.get("id", "")).strip(), str(r.get("per_ayah_url", ""))
            if not rid or "{SSS}" not in tpl or "{AAA}" not in tpl:
                warn("extra reciter %r skipped: needs id and per_ayah_url with {SSS} and {AAA}" % rid)
                continue
            if not r.get("source") or not r.get("licence"):
                warn("extra reciter %s skipped: source and licence are required" % rid)
                continue
            try:
                status, _ = fetch(tpl.replace("{SSS}", "001").replace("{AAA}", "001"), tries=2)
            except Exception as e:
                status = "error: %s" % e
            if status != 200:
                warn("extra reciter %s not confirmed (%s)" % (rid, status))
            reciters.append({
                "id": rid, "name": str(r.get("name", rid)), "folder": rid,
                "country": str(r.get("country", "")), "per_ayah_url": tpl,
                "verified": status == 200, "check_status": str(status), "checked_at": now,
                "timing": None, "source": str(r.get("source")), "licence": str(r.get("licence")),
                "attribution": str(r.get("attribution", ""))})
    attach_pictures(reciters)
    write_json(os.path.join(OUT, "reciters.json"), {"version": 1, "reciters": reciters})
    ok("reciters", "%d of %d confirmed" % (sum(1 for r in reciters if r["verified"]), len(reciters)))

    # Font
    font_entries = []
    family_of = {"fonts/AmiriQuran-Regular.ttf": "Amiri Quran"}
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

    for rel, family in build_google_fonts():
        font_entries.append(rel)
        family_of[rel] = family

    build_backgrounds()

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
        add(rel, "font", {"family": family_of.get(rel, "Amiri Quran")})
    write_json(os.path.join(OUT, "catalog.json"), {"version": 1, "built_at": now, "files": files})
    write_json(os.path.join(OUT, "report.json"), {
        "built_at": now, "ok": not errors, "errors": errors, "warnings": warnings, "checks": checks,
        "basmala_prefix_removed_from": stripped, "quranenc_arabic_letter_differences": mism})

    print("\nDone. errors=%d warnings=%d" % (len(errors), len(warnings)))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
