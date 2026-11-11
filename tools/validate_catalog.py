#!/usr/bin/env python3
"""Перевіряє catalog.json перед публікацією.

  python tools/validate_catalog.py [catalog.json] [--release] [--online]

Помилки зупиняють перевірку з кодом 1, попередження ні.
--release  перетворює «патча ще немає», демо-зображення та нерозв'язані примітки на помилки
--online   завантажує архіви з url і звіряє SHA256 (повільно, але це справжня перевірка)
"""
import argparse, hashlib, json, re, sys, urllib.request
from pathlib import Path

ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')
SHA_RE = re.compile(r'^[0-9a-fA-F]{64}$')
HTTP = re.compile(r'^https?://', re.I)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('catalog', nargs='?', default='catalog.json')
    ap.add_argument('--release', action='store_true')
    ap.add_argument('--online', action='store_true')
    a = ap.parse_args()
    try:
        cat = json.loads(Path(a.catalog).read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        sys.exit(f'ПОМИЛКА: не вдалося прочитати {a.catalog}: {e}')

    errors, warns = [], []
    err = errors.append
    soft = (errors if a.release else warns).append

    games = cat.get('games')
    if not isinstance(games, list) or not games:
        sys.exit('ПОМИЛКА: у каталозі немає списку games')
    ids = [g.get('id') for g in games if isinstance(g, dict)]
    for i in {x for x in ids if ids.count(x) > 1}:
        err(f'id «{i}» повторюється')

    for g in games:
        if not isinstance(g, dict):
            err('запис гри має бути об’єктом'); continue
        gid = g.get('id', '?')
        p = f'[{gid}]'
        if not (isinstance(g.get('id'), str) and ID_RE.match(g['id'])): err(f'{p} id має бути з малих латинських літер, цифр і дефісів')
        if not (isinstance(g.get('name'), str) and g['name'].strip()): err(f'{p} немає name')
        if not g.get('studio'): soft(f'{p} не вказано studio')
        h = g.get('hue')
        if not (isinstance(h, (int, float)) and not isinstance(h, bool) and 0 <= h <= 360): err(f'{p} hue має бути числом від 0 до 360')
        aid = g.get('steam_appid')
        if aid is not None and not (isinstance(aid, int) and aid > 0): err(f'{p} steam_appid має бути додатним числом або null')
        exe = g.get('exe')
        if not (isinstance(exe, list) and exe and all(isinstance(x, str) and x.lower().endswith('.exe') for x in exe)): err(f'{p} exe: список імен файлів .exe, за якими Ліхтар впізнає гру')
        if not (isinstance(g.get('folders'), list) and g['folders']): soft(f'{p} немає folders (буде використано name)')
        if g.get('_note'): soft(f'{p} нерозв’язана примітка: {g["_note"]}')
        if g.get('game_build') and not str(g['game_build']).isdigit(): err(f'{p} game_build має бути числом')
        pr = g.get('progress')
        if pr is not None and not (isinstance(pr, (int, float)) and 0 <= pr <= 100): err(f'{p} progress від 0 до 100')
        if g.get('status') not in (None, 'complete', 'partial', 'wip'): err(f'{p} status: complete, partial або wip')

        patch = [g.get('version'), g.get('url'), g.get('sha256'), g.get('size')]
        if not any(patch):
            soft(f'{p} патча ще немає (version, url, sha256, size порожні)')
        else:
            if not all(patch): err(f'{p} патч заповнено не повністю: потрібні version, url, sha256 і size разом')
            if g.get('url') and not HTTP.match(g['url']): err(f'{p} url має починатися з http(s)://')
            if g.get('sha256') and not SHA_RE.match(g['sha256']): err(f'{p} sha256 має бути 64 шістнадцятковими символами')
        for k, e in enumerate(g.get('log') or []):
            if not (isinstance(e, dict) and e.get('v') and e.get('d') and isinstance(e.get('i'), list) and e['i']): err(f'{p} log[{k}]: потрібні v, d і непорожній список i')
            elif not all(isinstance(x, list) and len(x) == 2 and x[1] for x in e['i']): err(f'{p} log[{k}]: кожен рядок має вигляд ["", "текст"]')
        if g.get('version') and g.get('log') and g['log'][0].get('v') != g['version']: soft(f'{p} перший запис історії ({g["log"][0].get("v")}) не збігається з version ({g["version"]})')
        c = g.get('compare')
        if c:
            for side in ('before', 'after'):
                u = str(c.get(side, ''))
                if u.startswith('data:'): soft(f'{p} compare.{side} це вбудована демо-картинка, замініть на посилання https')
                elif not u.startswith('https://'): err(f'{p} compare.{side} має бути посиланням https://')

    for k, n in enumerate(cat.get('news') or []):
        if not (n.get('t') and n.get('d')): err(f'news[{k}]: потрібні t і d')
        if n.get('u') and not HTTP.match(n['u']): err(f'news[{k}]: u має починатися з http(s)://')
        if n.get('game') and n['game'] not in ids: err(f'news[{k}]: game «{n["game"]}» не знайдено в каталозі')
    if cat.get('featured') and cat['featured'] not in ids: err(f'featured «{cat["featured"]}» не знайдено в каталозі')

    if a.online:
        for g in games:
            if not (g.get('url') and g.get('sha256')): continue
            h, n = hashlib.sha256(), 0
            try:
                req = urllib.request.Request(g['url'], headers={'User-Agent': 'lichtar-validate'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    while chunk := r.read(1 << 20):
                        h.update(chunk); n += len(chunk)
            except Exception as e:
                err(f'[{g["id"]}] не вдалося завантажити {g["url"]}: {e}'); continue
            if h.hexdigest().lower() != g['sha256'].lower(): err(f'[{g["id"]}] SHA256 архіву не збігається з каталогом')
            else: print(f'  [{g["id"]}] архів доступний, {n} байт, SHA256 збігається')

    for w in warns: print('Увага:   ', w)
    for e in errors: print('ПОМИЛКА: ', e)
    print(f'\nІгор: {len(games)}. Помилок: {len(errors)}, попереджень: {len(warns)}.' + (' Каталог готовий до публікації.' if not errors and not warns else ''))
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
