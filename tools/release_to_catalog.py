#!/usr/bin/env python3
"""Оновлює catalog.json, коли на GitHub опубліковано Release з патчем.

Тег релізу: <id-гри>-v<версія>, наприклад blood-west-v1.4.3
В релізі: zip-архів із файлами патча та опис зі списком змін (рядки з "-").
Необов'язково в описі: рядок "збірка: 12345678" (збірка Steam, на якій перевірено патч).

Запускається з GitHub Actions (бере подію з GITHUB_EVENT_PATH).
"""
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import urllib.request

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
TAG_RE = re.compile(r"^(?P<id>[a-z0-9][a-z0-9-]*?)-v(?P<ver>\d[0-9A-Za-z.+_-]*)$")


def parse_tag(tag):
    m = TAG_RE.match(tag or "")
    if not m:
        sys.exit(f"Тег «{tag}» не підходить. Потрібен формат <id-гри>-v<версія>, наприклад blood-west-v1.4.3")
    return m["id"], m["ver"]


def parse_notes(body):
    items, build = [], None
    for raw in (body or "").splitlines():
        line = raw.strip()
        m = re.match(r"^(?:build|збірка)\s*:\s*(\d+)\s*$", line, re.I)
        if m:
            build = m.group(1)
            continue
        m = re.match(r"^[-*•]\s+(.*\S)\s*$", line)
        if m:
            items.append(["", re.sub(r"^(fix|new)\s*:\s*", "", m.group(1), flags=re.I)])
    return items, build


def fmt_date(iso):
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else datetime.datetime.now()
    return f"{dt.day} {MONTHS[dt.month - 1]}"


def human_size(n):
    mb = n / 1048576
    return f"{mb:.1f}".replace(".", ",") + " МБ" if mb >= 1 else f"{max(1, round(n / 1024))} КБ"


def http_get(url, token=None, accept="*/*"):
    headers = {"User-Agent": "lichtar-release", "Accept": accept}
    if token and url.startswith("https://api.github.com"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def pick_asset(assets, game_id):
    zips = [a for a in assets or [] if a["name"].lower().endswith(".zip")]
    preferred = [a for a in zips if game_id in a["name"].lower()]
    return (preferred or zips or [None])[0]


def sha_and_size(url, token=None):
    h, n = hashlib.sha256(), 0
    with http_get(url, token) as r:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def update_catalog(cat, game_id, version, url, sha, size, items, date, build):
    game = next((g for g in cat.get("games", []) if g["id"] == game_id), None)
    if game is None:
        sys.exit(f"Гри «{game_id}» немає в catalog.json. Спочатку додайте її запис (див. RELEASING.md).")
    game.update(version=version, url=url, sha256=sha, size=size)
    if build:
        game["game_build"] = build
    log = [e for e in game.get("log", []) if e.get("v") != version]  # повторний запуск не дублює запис
    if items:
        log.insert(0, {"v": version, "d": date, "i": items})
    game["log"] = log
    return game


def main():
    event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
    rel = event["release"]
    if rel.get("prerelease"):
        print("Це пре-реліз, каталог не змінюємо.")
        return
    if re.match(r"^v\d", rel.get("tag_name") or ""):
        print("Це реліз самої програми (тег v...), каталог не змінюємо.")
        return
    game_id, version = parse_tag(rel["tag_name"])
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")

    asset = pick_asset(rel.get("assets"), game_id)
    for _ in range(6):  # архів іноді долучається за мить після події
        if asset or not repo:
            break
        time.sleep(10)
        data = json.load(http_get(f"https://api.github.com/repos/{repo}/releases/tags/{rel['tag_name']}", token, "application/vnd.github+json"))
        asset = pick_asset(data.get("assets"), game_id)
    if not asset:
        sys.exit("У релізі немає zip-архіву з патчем.")

    sha, n = sha_and_size(asset["browser_download_url"], token)
    items, build = parse_notes(rel.get("body"))
    path = pathlib.Path(os.environ.get("CATALOG_PATH", "catalog.json"))
    cat = json.loads(path.read_text(encoding="utf-8"))
    update_catalog(cat, game_id, version, asset["browser_download_url"], sha, human_size(n),
                   items, fmt_date(rel.get("published_at")), build)
    path.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{game_id} {version}: sha256={sha[:16]}…, {human_size(n)}, змін у записі: {len(items)}")


if __name__ == "__main__":
    main()
