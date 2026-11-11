#!/usr/bin/env python3
"""Підказує, що вписати в catalog.json для встановленої гри: exe, теку, Steam appid, збірку.

  python tools/inspect_game.py "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blood West"

Працює і з піратськими копіями: тоді appid береться лише з steam_appid.txt, якщо він там є.
"""
import json, re, sys, zlib
from pathlib import Path

SKIP = re.compile(r'(unins|uninstall|crash|vc_?redist|dxsetup|dotnet|setup|helper|easyanticheat|installer|notification_helper)', re.I)


def find_appid(game):
    f = game / 'steam_appid.txt'
    if f.is_file():
        t = f.read_text(errors='ignore').strip()
        if t.isdigit():
            return int(t), 'steam_appid.txt', None
    for parent in game.parents:
        if parent.name.lower() == 'common' and parent.parent.name.lower() == 'steamapps':
            for acf in parent.parent.glob('appmanifest_*.acf'):
                t = acf.read_text(errors='ignore')
                m = re.search(r'"installdir"\s+"([^"]+)"', t)
                if m and m.group(1).lower() == game.name.lower():
                    a, b = re.search(r'"appid"\s+"(\d+)"', t), re.search(r'"buildid"\s+"(\d+)"', t)
                    return int(a.group(1)), acf.name, (b.group(1) if b else None)
    return None, None, None


def engine(game):
    names = {p.name.lower() for p in game.iterdir()}
    if 'unityplayer.dll' in names or any(n.endswith('_data') for n in names): return 'Unity'
    if 'data.win' in names: return 'GameMaker'
    if any(n.endswith('.pck') for n in names): return 'Godot'
    if (game / 'Engine').is_dir() or any((game / d / 'Binaries').is_dir() for d in names if (game / d).is_dir()): return 'Unreal'
    return 'не визначено'


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    game = Path(sys.argv[1]).expanduser().resolve()
    if not game.is_dir():
        sys.exit(f'Немає теки {game}')
    exes = sorted([p.name for p in game.glob('*.exe') if not SKIP.search(p.name)], key=lambda n: (game.name.lower().replace(' ', '') not in n.lower().replace(' ', '').replace('_', ''), n.lower()))
    deep = sorted(str(p.relative_to(game)).replace('\\', '/') for p in game.glob('*/Binaries/Win64/*-Shipping.exe'))
    appid, src, build = find_appid(game)
    slug = re.sub(r'[^a-z0-9]+', '-', game.name.lower()).strip('-') or 'game'
    hue = zlib.crc32(game.name.encode()) % 360
    print(f'Тека гри   : {game}')
    print(f'Рушій      : {engine(game)}')
    print(f'Exe у корені: {", ".join(exes) or "нема"}' + (f'   (глибше: {", ".join(deep)})' if deep else ''))
    print(f'Steam appid: {appid if appid else "не знайдено"}' + (f'   (джерело: {src})' if src else ''))
    print(f'Збірка Steam: {build or "не знайдено"}')
    print('\nЗапис для catalog.json (вкажіть студію, перевірте exe):\n')
    entry = {'id': slug, 'name': game.name, 'studio': '', 'hue': hue, 'steam_appid': appid, 'exe': exes[:2] or [''], 'folders': [game.name],
             **({'game_build': build} if build else {}), 'version': '', 'size': '', 'url': '', 'sha256': '', 'log': []}
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
