import re

PLUGIN = {
    "id": "plugin.custom-themes",
    "name": "Custom Themes",
    "version": "1.1.0",
    "author": "easy-flasher",
    "description": "Создание и применение кастомных тем из окна Themes",
}


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(round(v))))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (hex_color or '').strip())
    if not m:
        return (34, 211, 238)  # fallback neon cyan
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}"


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        _clamp(a[0] * (1 - t) + b[0] * t),
        _clamp(a[1] * (1 - t) + b[1] * t),
        _clamp(a[2] * (1 - t) + b[2] * t),
    )


def _darken(rgb: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return _mix(rgb, (0, 0, 0), t)


def _lighten(rgb: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return _mix(rgb, (255, 255, 255), t)


def _generate_palette(primary_hex: str, secondary_hex: str) -> dict:
    p = _hex_to_rgb(primary_hex)
    s = _hex_to_rgb(secondary_hex)
    neon = _rgb_to_hex(_lighten(p, 0.05))
    bg = _rgb_to_hex(_darken(_mix(p, s, 0.35), 0.82))
    accent = _rgb_to_hex(_lighten(s, 0.15))
    soft = _rgb_to_hex(_lighten(p, 0.35))
    ring = _rgb_to_hex(_mix(p, (255, 255, 255), 0.15))
    shadow = _rgb_to_hex(_mix(p, (0, 0, 0), 0.85))
    return {
        "neon": neon,
        "bg": bg,
        "accent": accent,
        "soft": soft,
        "ring": ring,
        "shadow": shadow,
    }


def register(eel):
    # UI теперь добавляется ассетами из web/, тут ничего не экспонируем
    pass


# ---------------- Storage ----------------
import os
import json

def _store_path() -> str:
    base = os.path.join(os.getcwd(), 'plugins')
    return os.path.join(base, 'custom_theme_store.json')

def _load_store() -> dict:
    try:
        with open(_store_path(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"themes": [], "last": None}

def _save_store(data: dict) -> None:
    try:
        with open(_store_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_palette(name: str, primary: str, secondary: str) -> dict:
    name = (name or '').strip() or 'Custom Theme'
    pal = _generate_palette(primary, secondary)
    store = _load_store()
    # replace if exists
    exists = False
    for t in store.get('themes', []):
        if t.get('name') == name:
            t.update({"primary": primary, "secondary": secondary, "palette": pal})
            exists = True
            break
    if not exists:
        store.setdefault('themes', []).append({
            "name": name,
            "primary": primary,
            "secondary": secondary,
            "palette": pal,
        })
    store['last'] = name
    _save_store(store)
    return {"ok": True, "saved": {"name": name, "palette": pal}}


def _list_palettes() -> dict:
    s = _load_store()
    return {"ok": True, "themes": s.get('themes', []), "last": s.get('last')}


def _delete_palette(name: str) -> dict:
    s = _load_store()
    before = len(s.get('themes', []))
    s['themes'] = [t for t in s.get('themes', []) if t.get('name') != name]
    if s.get('last') == name:
        s['last'] = None
    _save_store(s)
    return {"ok": True, "removed": before - len(s['themes'])}


def _get_last() -> dict:
    s = _load_store()
    last = s.get('last')
    for t in s.get('themes', []):
        if t.get('name') == last:
            return {"ok": True, "theme": t}
    return {"ok": True, "theme": None}


PLUGIN_API = {
    'ct_generate_palette': lambda primary, secondary: ({"ok": True, "palette": _generate_palette(primary, secondary)}),
    'ct_save_palette': _save_palette,
    'ct_list_palettes': _list_palettes,
    'ct_delete_palette': _delete_palette,
    'ct_get_last_palette': _get_last,
}

import re

PLUGIN = {
    "id": "plugin.custom-themes",
    "name": "Custom Themes",
    "version": "1.0.0",
    "author": "easy-flasher",
    "description": "Позволяет создавать и применять кастомные темы по двум цветам",
}


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(round(v))))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (hex_color or '').strip())
    if not m:
        return (34, 211, 238)  # fallback neon cyan
    h = m.group(1)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{_clamp(r):02x}{_clamp(g):02x}{_clamp(b):02x}"


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        _clamp(a[0] * (1 - t) + b[0] * t),
        _clamp(a[1] * (1 - t) + b[1] * t),
        _clamp(a[2] * (1 - t) + b[2] * t),
    )


def _darken(rgb: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return _mix(rgb, (0, 0, 0), t)


def _lighten(rgb: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return _mix(rgb, (255, 255, 255), t)


def _generate_palette(primary_hex: str, secondary_hex: str) -> dict:
    p = _hex_to_rgb(primary_hex)
    s = _hex_to_rgb(secondary_hex)
    neon = _rgb_to_hex(_lighten(p, 0.05))
    bg = _rgb_to_hex(_darken(_mix(p, s, 0.35), 0.82))
    accent = _rgb_to_hex(_lighten(s, 0.15))
    soft = _rgb_to_hex(_lighten(p, 0.35))
    ring = _rgb_to_hex(_mix(p, (255, 255, 255), 0.15))
    shadow = _rgb_to_hex(_mix(p, (0, 0, 0), 0.85))
    return {
        "neon": neon,
        "bg": bg,
        "accent": accent,
        "soft": soft,
        "ring": ring,
        "shadow": shadow,
    }


def register(eel):
    # expose nothing here; use PLUGIN_API
    pass


# ---------------- Storage ----------------
import os
import json

def _store_path() -> str:
    base = os.path.join(os.getcwd(), 'plugins')
    return os.path.join(base, 'custom_theme_store.json')

def _load_store() -> dict:
    try:
        with open(_store_path(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"themes": [], "last": None}

def _save_store(data: dict) -> None:
    try:
        with open(_store_path(), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _save_palette(name: str, primary: str, secondary: str) -> dict:
    name = (name or '').strip() or 'Custom Theme'
    pal = _generate_palette(primary, secondary)
    store = _load_store()
    # replace if exists
    exists = False
    for t in store.get('themes', []):
        if t.get('name') == name:
            t.update({"primary": primary, "secondary": secondary, "palette": pal})
            exists = True
            break
    if not exists:
        store.setdefault('themes', []).append({
            "name": name,
            "primary": primary,
            "secondary": secondary,
            "palette": pal,
        })
    store['last'] = name
    _save_store(store)
    return {"ok": True, "saved": {"name": name, "palette": pal}}


def _list_palettes() -> dict:
    s = _load_store()
    return {"ok": True, "themes": s.get('themes', []), "last": s.get('last')}


def _delete_palette(name: str) -> dict:
    s = _load_store()
    before = len(s.get('themes', []))
    s['themes'] = [t for t in s.get('themes', []) if t.get('name') != name]
    if s.get('last') == name:
        s['last'] = None
    _save_store(s)
    return {"ok": True, "removed": before - len(s['themes'])}


def _get_last() -> dict:
    s = _load_store()
    last = s.get('last')
    for t in s.get('themes', []):
        if t.get('name') == last:
            return {"ok": True, "theme": t}
    return {"ok": True, "theme": None}


PLUGIN_API = {
    'ct_generate_palette': lambda primary, secondary: (
        {"ok": True, "palette": _generate_palette(primary, secondary)}
    ),
    'ct_save_palette': _save_palette,
    'ct_list_palettes': _list_palettes,
    'ct_delete_palette': _delete_palette,
    'ct_get_last_palette': _get_last,
}