#!/usr/bin/env python3
"""Додає або оновлює гру в catalog.json після випуску нового патча.

  python tools/lichtar_release.py blood-west 1.4.3 BloodWest_UA_1.4.3.zip \
      --url https://github.com/USER/REPO/releases/download/blood-west-1.4.3/BloodWest_UA_1.4.3.zip \
      --note "Виправлено діалоги торговця" --note "new:Додано переклад підказок"

Скрипт рахує SHA256 і розмір архіву, піднімає версію й дописує запис у журнал змін.
Префікси приміток: fix:, new: (без префікса звичайний рядок).
"""
import argparse, datetime, hashlib, json, pathlib, sys

MONTHS = ["січня","лютого","березня","квітня","травня","червня","липня","серпня","вересня","жовтня","листопада","грудня"]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_id"); ap.add_argument("version"); ap.add_argument("zip")
    ap.add_argument("--url", required=True, help="пряме посилання на архів у релізі")
    ap.add_argument("--catalog", default="catalog.json")
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--game-build", help="збірка Steam (buildid), для якої перевірено патч")
    a = ap.parse_args()

    z = pathlib.Path(a.zip)
    if not z.is_file(): sys.exit(f"Немає файлу {z}")
    h = hashlib.sha256()
    with z.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    mb = z.stat().st_size / 1048576
    size = f"{mb:.1f}".replace(".", ",") + " МБ" if mb >= 1 else f"{max(1, round(z.stat().st_size / 1024))} КБ"

    cp = pathlib.Path(a.catalog)
    cat = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {"news": [], "games": []}
    game = next((g for g in cat["games"] if g["id"] == a.game_id), None)
    if game is None: sys.exit(f"Гри «{a.game_id}» немає в каталозі. Спочатку додайте її запис (name, steam_appid, exe, folders, hue).")

    game.update(version=a.version, url=a.url, sha256=h.hexdigest(), size=size)
    if a.game_build: game["game_build"] = a.game_build
    now = datetime.date.today()
    items = []
    for n in a.note:
        kind, _, text = n.partition(":")
        items.append([kind, text] if kind in ("fix", "new") and text else ["", n])
    if items:
        game.setdefault("log", []).insert(0, {"v": a.version, "d": f"{now.day} {MONTHS[now.month-1]}", "i": items})
    cp.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{a.game_id} {a.version}: sha256={h.hexdigest()[:16]}…, {size}")

if __name__ == "__main__":
    main()
