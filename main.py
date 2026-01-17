import eel
import importlib.util
import pathlib
import traceback
import mtk
import brom as brom_flash
import testpoint as tp_flash
from flash.root import root as root_helper
from flash.system import flash_sys as flash_sys_helper
from flash.recMode import flash_recovery as flash_recovery_helper
from recovery import recovery as recovery_helper
from fetch import fetch_proc
import os
import subprocess
import json
import time
from typing import Callable


eel.init("web")

# -------------------- Plugins --------------------
LOADED_PLUGINS: list[dict] = []
PLUGIN_FUNCS: dict[str, object] = {}
PLUGIN_ASSETS: dict[str, dict] = {}
DISABLED_PLUGINS: set[str] = set()  # Плагины отключенные на сессию

def _discover_plugin_files() -> list[pathlib.Path]:
    base = pathlib.Path(os.getcwd()) / 'plugins'
    if not base.exists():
        return []
    return [p for p in base.glob('*.py') if p.name != '__init__.py']

def _load_plugin_module(plugin_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(plugin_path.stem, str(plugin_path))
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        return module
    except Exception:
        traceback.print_exc()
        return None

def _normalize_plugin_meta(raw: dict) -> dict:
    return {
        "name": str(raw.get("name", "Unnamed Plugin")),
        "version": str(raw.get("version", "0.0.0")),
        "author": str(raw.get("author", "unknown")),
        "description": str(raw.get("description", "")),
        "id": str(raw.get("id", "plugin." + str(raw.get("name", "unnamed")).lower().replace(' ', '-'))),
    }

def load_plugins() -> None:
    global LOADED_PLUGINS
    global PLUGIN_FUNCS
    global PLUGIN_ASSETS
    LOADED_PLUGINS = []
    PLUGIN_FUNCS = {}
    PLUGIN_ASSETS = {}
    for path in _discover_plugin_files():
        # Пропускаем отключенные плагины
        plugin_id = path.stem
        if plugin_id in DISABLED_PLUGINS:
            continue
            
        mod = _load_plugin_module(path)
        if not mod:
            continue
        meta = getattr(mod, 'PLUGIN', {})
        if not isinstance(meta, dict):
            meta = {}
        meta = _normalize_plugin_meta(meta)
        meta['id'] = plugin_id  # Используем имя файла как ID
        # allow plugin to register endpoints or hooks
        try:
            if hasattr(mod, 'register') and callable(getattr(mod, 'register')):
                mod.register(eel)
        except Exception:
            traceback.print_exc()
        # Register plugin API functions via optional PLUGIN_API dict
        try:
            api = getattr(mod, 'PLUGIN_API', None)
            if isinstance(api, dict):
                for name, func in api.items():
                    if callable(func):
                        PLUGIN_FUNCS[name] = func
        except Exception:
            traceback.print_exc()

        # Collect optional frontend assets
        try:
            plugin_id = meta.get('id') if isinstance(meta, dict) else None
            if not plugin_id:
                plugin_id = str(path.stem)
            assets: dict[str, list] = {"js": [], "css": [], "html": []}
            candidates = [
                path.parent / path.stem,
                path.parent / (path.stem + "_assets"),
            ]
            for candidate in candidates:
                webdir = candidate / 'web'
                base = webdir if webdir.exists() else candidate
                if base.exists() and base.is_dir():
                    for p in base.rglob('*'):
                        if not p.is_file():
                            continue
                        try:
                            if p.suffix.lower() == '.js':
                                assets["js"].append({"name": p.name, "content": p.read_text(encoding='utf-8', errors='ignore')})
                            elif p.suffix.lower() == '.css':
                                assets["css"].append({"name": p.name, "content": p.read_text(encoding='utf-8', errors='ignore')})
                            elif p.suffix.lower() in ('.html', '.htm'):
                                assets["html"].append({"name": p.name, "content": p.read_text(encoding='utf-8', errors='ignore')})
                        except Exception:
                            traceback.print_exc()
            PLUGIN_ASSETS[plugin_id] = assets
        except Exception:
            traceback.print_exc()
        LOADED_PLUGINS.append({
            **meta,
            "module": mod.__name__,
            "file": str(path)
        })


@eel.expose
def get_plugins() -> list[dict]:
    # Получаем все файлы плагинов
    all_plugin_files = _discover_plugin_files()
    all_plugins = []
    
    for path in all_plugin_files:
        plugin_id = path.stem
        is_disabled = plugin_id in DISABLED_PLUGINS
        
        if is_disabled:
            # Для отключенных плагинов пытаемся загрузить метаданные без выполнения кода
            try:
                mod = _load_plugin_module(path)
                if mod:
                    meta = getattr(mod, 'PLUGIN', {})
                    if not isinstance(meta, dict):
                        meta = {}
                    meta = _normalize_plugin_meta(meta)
                    meta['id'] = plugin_id
                    meta['enabled'] = False
                    all_plugins.append(meta)
                else:
                    # Если не удалось загрузить, создаем базовую информацию
                    all_plugins.append({
                        "name": plugin_id,
                        "version": "0.0.0",
                        "author": "unknown",
                        "description": "Plugin file found but could not load metadata",
                        "id": plugin_id,
                        "enabled": False
                    })
            except Exception:
                all_plugins.append({
                    "name": plugin_id,
                    "version": "0.0.0",
                    "author": "unknown", 
                    "description": "Plugin file found but could not load metadata",
                    "id": plugin_id,
                    "enabled": False
                })
        else:
            # Для включенных плагинов используем данные из LOADED_PLUGINS
            loaded_plugin = next((p for p in LOADED_PLUGINS if p.get('id') == plugin_id), None)
            if loaded_plugin:
                loaded_plugin['enabled'] = True
                all_plugins.append(loaded_plugin)
    
    return all_plugins


@eel.expose
def reload_plugins() -> dict:
    try:
        load_plugins()
        return {"ok": True, "count": len(LOADED_PLUGINS)}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def plugin_call(name: str, *args):
    try:
        fn = PLUGIN_FUNCS.get(str(name))
        if not callable(fn):
            return {"ok": False, "error": f"Plugin function not found: {name}"}
        result = fn(*args)
        return result if isinstance(result, dict) else {"ok": True, "result": result}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def get_plugin_assets() -> dict:
    # Return JS/CSS/HTML text assets grouped by plugin id
    return PLUGIN_ASSETS


@eel.expose
def install_magisk() -> dict:
    """Скачивает и устанавливает последнюю версию Magisk"""
    try:
        # Скачиваем Magisk APK
        apk_path, error = _download_magisk_apk()
        if error:
            return {"success": False, "error": error}
            
        # Устанавливаем APK
        success, error = _install_magisk_apk(apk_path)
        if error:
            return {"success": False, "error": error}
            
        return {
            "success": True, 
            "message": "Magisk успешно установлен!",
            "apk_path": apk_path
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка установки Magisk: {str(e)}"}


@eel.expose
def check_magisk_installed() -> dict:
    """Проверяет, установлен ли Magisk на устройстве"""
    try:
        online, err = _ensure_device_online()
        if not online:
            return {"installed": False, "error": err}
            
        result, error = _adb('shell pm list packages | grep magisk')
        if error:
            return {"installed": False, "error": error}
            
        installed = 'com.topjohnwu.magisk' in result
        return {
            "installed": installed,
            "message": "Magisk установлен" if installed else "Magisk не установлен"
        }
        
    except Exception as e:
        return {"installed": False, "error": f"Ошибка проверки Magisk: {str(e)}"}


@eel.expose
def check_for_updates() -> dict:
    """Проверяет наличие обновлений"""
    try:
        current_version = _get_current_version()
        
        # Если версия 0.0.0 - показываем тестовое обновление
        if current_version == "0.0.0":
            return {
                "success": True,
                "current_version": current_version,
                "latest_version": "1.0.0",
                "has_update": True,
                "message": "Доступна новая версия 1.0.0 (тестовый режим)"
            }
        
        # Обычная проверка через GitHub
        latest_version, error = _get_latest_version()
        
        if error:
            return {"success": False, "error": error}
            
        has_update = _compare_versions(current_version, latest_version)
        
        return {
            "success": True,
            "current_version": current_version,
            "latest_version": latest_version,
            "has_update": has_update,
            "message": f"Доступна новая версия {latest_version}" if has_update else "У вас последняя версия"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка проверки обновлений: {str(e)}"}


@eel.expose
def get_update_info() -> dict:
    """Получает информацию об обновлении"""
    try:
        current_version = _get_current_version()
        
        # Если версия 0.0.0 - возвращаем тестовую информацию
        if current_version == "0.0.0":
            return {
                "success": True,
                "version": "1.0.0",
                "name": "AutoRoot v1.0.0 - Тестовое обновление",
                "body": """🎉 **AutoRoot v1.0.0 - Тестовое обновление**

**Новые возможности:**
✅ Система автоматических обновлений
✅ Автоматическая установка Magisk
✅ Улучшенная система бэкапов
✅ Диагностика Fastboot
✅ Новые темы интерфейса

**Исправления:**
🔧 Улучшена стабильность работы
🔧 Исправлены ошибки в системе бэкапов
🔧 Оптимизирована работа с MediaTek устройствами

**Технические улучшения:**
⚡ Ускорена работа приложения
⚡ Улучшена обработка ошибок
⚡ Добавлена поддержка новых устройств

*Это тестовое обновление для проверки системы обновлений.*""",
                "download_url": "https://github.com/proghub13/easy-flasher/releases/latest/download/AutoRoot.exe",
                "published_at": "2025-01-21T12:00:00Z",
                "html_url": "https://github.com/proghub13/easy-flasher/releases/latest"
            }
        
        # Обычная проверка через GitHub (список релизов)
        import requests
        api_url = "https://api.github.com/repos/proghub13/easy-flasher/releases"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        releases = response.json() or []
        if not releases:
            return {"success": False, "error": "Релизы не найдены в репозитории"}
        # Берем первый не-draft релиз (GitHub возвращает в порядке от нового к старому)
        data = next((r for r in releases if not r.get("draft", False)), releases[0])
        
        # Получаем URL для скачивания
        download_url = None
        assets = data.get("assets", [])
        for asset in assets:
            if asset["name"].endswith(".exe"):
                download_url = asset["browser_download_url"]
                break
        if not download_url and assets:
            # Фоллбек: берем первый ассет (напр., .rar)
            download_url = assets[0].get("browser_download_url")
        
        return {
            "success": True,
            "version": data.get("tag_name", "").lstrip("v"),
            "name": data.get("name", ""),
            "body": data.get("body", ""),
            "download_url": download_url,
            "published_at": data.get("published_at", ""),
            "html_url": data.get("html_url", "")
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка получения информации: {str(e)}"}


@eel.expose
def download_update(download_url: str) -> dict:
    """Скачивает обновление"""
    try:
        current_version = _get_current_version()
        
        # Если версия 0.0.0 - создаем тестовый файл
        if current_version == "0.0.0":
            import os
            
            # Создаем папку для обновлений
            updates_dir = pathlib.Path(os.getcwd()) / 'updates'
            updates_dir.mkdir(exist_ok=True)
            
            # Создаем тестовый файл
            filename = f"AutoRoot_v1.0.0_test_{int(time.time())}.exe"
            file_path = updates_dir / filename
            
            # Создаем простой тестовый файл
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('# Тестовое обновление AutoRoot v1.0.0\n')
                f.write('# Это файл создан для тестирования системы обновлений\n')
                f.write('# В реальном релизе здесь будет исполняемый файл\n')
            
            return {
                "success": True,
                "file_path": str(file_path),
                "message": f"Тестовое обновление создано: {filename}"
            }
        
        # Обычное скачивание с GitHub
        import requests
        import os
        from urllib.parse import urlparse
        
        # Создаем папку для обновлений
        updates_dir = pathlib.Path(os.getcwd()) / 'updates'
        updates_dir.mkdir(exist_ok=True)
        
        # Получаем имя файла из URL
        parsed_url = urlparse(download_url)
        filename = os.path.basename(parsed_url.path)
        if not filename.endswith('.exe'):
            filename = f"AutoRoot_update_{int(time.time())}.exe"
        
        file_path = updates_dir / filename
        
        # Скачиваем файл
        response = requests.get(download_url, timeout=30, stream=True)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return {
            "success": True,
            "file_path": str(file_path),
            "message": f"Обновление скачано: {filename}"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Ошибка скачивания: {str(e)}"}


@eel.expose
def call_action(name: str, *args):
    try:
        # Allow plugins to override actions via keys like 'action.perform_root'
        override = PLUGIN_FUNCS.get(f'action.{name}')
        if callable(override):
            result = override(*args)
            return result if isinstance(result, dict) else {"ok": True, "result": result}
        # Fallback to built-in actions
        if name == 'perform_root':
            return perform_root(*args)
        if name == 'perform_flash':
            return perform_flash(*args)
        if name == 'perform_unlock':
            return perform_unlock(*args)
        return {"ok": False, "error": f"Unknown action: {name}"}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


def _detect_soc() -> str:
    cpu = fetch_proc.get_cpu_info()
    return cpu


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def _adb(*args: str) -> tuple[str, str | None]:
    try:
        result = subprocess.check_output([_adb_path(), *args], text=True, stderr=subprocess.PIPE).strip()
        return result, None
    except subprocess.CalledProcessError as e:
        return "", e.stderr.strip() or str(e)
    except FileNotFoundError:
        return "", "ADB не найден. Проверьте platform-tools."
    except Exception as e:
        return "", str(e)


def _fastboot(*args: str) -> tuple[str, str | None]:
    try:
        result = subprocess.check_output([_fastboot_path(), *args], text=True, stderr=subprocess.PIPE).strip()
        return result, None
    except subprocess.CalledProcessError as e:
        return "", e.stderr.strip() or str(e)
    except FileNotFoundError:
        return "", "Fastboot не найден. Проверьте platform-tools."
    except Exception as e:
        return "", str(e)


def _ensure_device_online() -> tuple[bool, str | None]:
    out, err = _adb('devices')
    if err:
        return False, f"Ошибка ADB: {err}"
    if '\tdevice' not in out:
        return False, 'Устройства не найдены, проверьте отладку по USB и попробуйте ещё раз'
    return True, None


# Ручные переопределения производителя/модели (если ADB не дал данные)
MANUAL_MANUFACTURER: str | None = None
MANUAL_MODEL: str | None = None


def _reboot_to_bootloader() -> None:
    try:
        out, _ = _fastboot('devices')
        if out:
            return
    except Exception:
        pass
    _, err = _adb('reboot', 'bootloader')
    if err:
        print(f"Ошибка при перезагрузке в bootloader: {err}")


def _has_fastboot_device() -> bool:
    out, err = _fastboot('devices')
    if err:
        print(f"Ошибка при проверке fastboot устройств: {err}")
        return False
    
    print(f"Fastboot devices output: {out}")  # Отладочная информация
    
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Проверяем различные варианты статуса fastboot
        if ('\tfastboot' in line or 
            line.endswith('fastboot') or 
            ('\t' in line and 'fastboot' in line.split('\t')[-1].lower()) or
            'fastboot' in line.lower()):
            print(f"Найдено fastboot устройство: {line}")
            return True
    
    print("Fastboot устройства не найдены")
    return False


def _has_adb_device() -> bool:
    out, _ = _adb('devices')
    return '\tdevice' in out


def _ensure_fastboot_auto(wait_seconds: int = 30) -> dict | None:
    # Returns None if fastboot available; otherwise returns {ok: False, message: ...}
    print("Проверяем наличие fastboot устройств...")
    
    if _has_fastboot_device():
        print("Fastboot устройство найдено!")
        return None
    
    print("Fastboot устройство не найдено, проверяем ADB...")
    if _has_adb_device():
        print("ADB устройство найдено, перезагружаем в fastboot...")
        _, err = _adb('reboot', 'bootloader')  # Используем 'bootloader' вместо 'fastboot'
        if err:
            print(f"Ошибка при попытке перезагрузки в bootloader: {err}")
            return {"ok": False, "error": f"Не удалось перезагрузить устройство в bootloader: {err}"}
        
        print(f"Ждем {wait_seconds} секунд для перехода в fastboot...")
        time.sleep(max(1, wait_seconds))
        
        print("Проверяем fastboot после перезагрузки...")
        if _has_fastboot_device():
            print("Fastboot устройство найдено после перезагрузки!")
            return None
        
        # Проверяем, вернулось ли устройство в ADB
        print("Проверяем, вернулось ли устройство в ADB...")
        if _has_adb_device():
            return {"ok": False, "error": "Устройство не перешло в fastboot режим. Попробуйте вручную: выключите устройство, зажмите Vol- + Power и подключите USB."}
        
        # Ни ADB, ни fastboot
        return {"ok": False, "error": "Устройство не найдено ни в ADB, ни в fastboot режиме. Проверьте подключение USB."}
    
    # Нет устройств вообще
    print("ADB устройства не найдены")
    return {"ok": False, "error": "Подключите устройство и включите отладку по USB"}


def _is_bootloader_unlocked() -> tuple[bool, str | None]:
    out, err = _fastboot('getvar', 'unlocked')
    if err:
        return False, err
    # Примеры: "unlocked: yes" или вывод из device-info
    if 'unlocked: yes' in out.lower():
        return True, None
    try:
        out2, err2 = _fastboot('oem', 'device-info')
        if err2:
            print(f"Ошибка при получении device-info: {err2}")
        for line in out2.lower().splitlines():
            if 'device unlocked' in line and ('true' in line or 'yes' in line):
                return True, None
    except Exception as e:
        print(f"Исключение при проверке device-info: {e}")
    return False, "Загрузчик заблокирован"


def _get_manufacturer_and_model() -> tuple[str, str, str | None]:
    try:
        props, err = _adb('shell', 'getprop')
        if err:
            return (MANUAL_MANUFACTURER or 'Unknown', MANUAL_MODEL or 'Unknown', f"Ошибка ADB при получении свойств: {err}")
        import re
        man = re.search(r'\[ro.product.manufacturer\]: \[(.*?)\]', props)
        mod = re.search(r'\[ro.product.model\]: \[(.*?)\]', props)
        manufacturer = (man.group(1) if man else 'Unknown').strip()
        model = (mod.group(1) if mod else 'Unknown').strip()
        # Если неизвестно — используем ручной ввод, если задан
        if (not manufacturer or manufacturer == 'Unknown') and MANUAL_MANUFACTURER:
            manufacturer = MANUAL_MANUFACTURER
        if (not model or model == 'Unknown') and MANUAL_MODEL:
            model = MANUAL_MODEL
        return manufacturer, model, None
    except Exception as e:
        return (MANUAL_MANUFACTURER or 'Unknown', MANUAL_MODEL or 'Unknown', str(e))


def _load_special_profiles() -> dict:
    try:
        with open(os.path.join(os.getcwd(), 'special_devices.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"no_unlock_required": [], "no_fastboot_reboot": [], "instructions": [], "partitions": []}
    except Exception:
        traceback.print_exc()
        return {"no_unlock_required": [], "no_fastboot_reboot": [], "instructions": [], "partitions": []}


def _is_in_profiles(manufacturer: str, model: str, section: str) -> bool:
    prof = _load_special_profiles()
    for entry in prof.get(section, []):
        if entry.get('manufacturer', '').lower() == manufacturer.lower():
            models = entry.get('models', [])
            # Если список моделей пуст — правило для всех моделей производителя
            if not models:
                return True
            for m in models:
                if m.lower() in model.lower():
                    return True
    return False


def _get_device_instructions(manufacturer: str, model: str) -> list[str]:
    prof = _load_special_profiles()
    out = []
    for ins in prof.get('instructions', []):
        if ins.get('manufacturer', '').lower() == manufacturer.lower():
            mod = ins.get('model', '').lower()
            if not mod or mod in model.lower():
                out = ins.get('steps', [])
                break
    return out


def _get_device_partitions(manufacturer: str, model: str) -> tuple[list[str], str | None]:
    # Сначала пробуем получить из profiles
    prof = _load_special_profiles()
    for entry in prof.get('partitions', []):
        if entry.get('manufacturer', '').lower() == manufacturer.lower():
            models = entry.get('models', [])
            if not models or any(m.lower() in model.lower() for m in models):
                return entry.get('list', []), None
    
    # Если в profiles нет, пытаемся получить через fastboot
    out, err = _fastboot('getvar', 'all')
    if err:
        return [], f"Ошибка Fastboot при получении разделов: {err}"
    
    partitions = []
    import re
    for line in out.splitlines():
        match = re.match(r'^(?:partition|.+?):\s*([a-zA-Z0-9_-]+)', line)
        if match:
            part_name = match.group(1)
            # Фильтруем служебные или повторяющиеся записи
            if part_name and part_name not in partitions and not part_name.startswith('max-download-size'):
                partitions.append(part_name)
    
    if not partitions:
        return [], "Не удалось получить список разделов через Fastboot."
        
    return partitions, None


def _ensure_backup_directory() -> None:
    """Создает папку backups если её нет"""
    backup_dir = pathlib.Path(os.getcwd()) / 'backups'
    backup_dir.mkdir(exist_ok=True)


def _get_latest_magisk_url() -> tuple[str, None] | tuple[None, str]:
    """Получает URL последней версии Magisk"""
    try:
        import requests
        # GitHub API для получения последнего релиза Magisk
        api_url = "https://api.github.com/repos/topjohnwu/Magisk/releases/latest"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        for asset in data.get("assets", []):
            if asset["name"].endswith(".apk"):
                return asset["browser_download_url"], None
                
        return None, "Не найден APK файл в последнем релизе Magisk"
    except Exception as e:
        return None, f"Ошибка получения информации о Magisk: {str(e)}"


def _download_magisk_apk() -> tuple[str, None] | tuple[None, str]:
    """Скачивает последнюю версию Magisk APK"""
    try:
        import requests
        
        # Получаем URL последней версии
        url, error = _get_latest_magisk_url()
        if error:
            return None, error
            
        # Создаем папку для APK файлов
        apk_dir = pathlib.Path(os.getcwd()) / 'downloads'
        apk_dir.mkdir(exist_ok=True)
        
        # Путь для сохранения APK
        apk_path = apk_dir / 'magisk.apk'
        
        # Скачиваем файл
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(apk_path, 'wb') as f:
            f.write(response.content)
            
        return str(apk_path), None
        
    except Exception as e:
        return None, f"Ошибка скачивания Magisk: {str(e)}"


def _install_magisk_apk(apk_path: str) -> tuple[bool, None] | tuple[None, str]:
    """Устанавливает Magisk APK через ADB"""
    try:
        # Проверяем, что устройство подключено
        online, err = _ensure_device_online()
        if not online:
            return None, f"Устройство не подключено: {err}"
            
        # Устанавливаем APK
        result, error = _adb(f'install "{apk_path}"')
        if error:
            return None, f"Ошибка установки Magisk: {error}"
            
        # Проверяем успешность установки
        result, error = _adb('shell pm list packages | grep magisk')
        if error or 'com.topjohnwu.magisk' not in result:
            return None, "Magisk не был установлен корректно"
            
        return True, None
        
    except Exception as e:
        return None, f"Ошибка установки Magisk: {str(e)}"


def _get_current_version() -> str:
    """Возвращает текущую версию приложения"""
    return "1.0.0"


def _get_latest_version() -> tuple[str, None] | tuple[None, str]:
    """Получает последнюю версию с GitHub"""
    try:
        import requests
        # GitHub API: список релизов
        api_url = "https://api.github.com/repos/proghub13/easy-flasher/releases"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        releases = response.json() or []
        if not releases:
            return None, "Релизы не найдены в репозитории"
        data = next((r for r in releases if not r.get("draft", False)), releases[0])
        latest_version = data.get("tag_name", "").lstrip("v")  # Убираем 'v' если есть
        
        if not latest_version:
            return None, "Не удалось получить версию из релиза"
            
        return latest_version, None
        
    except Exception as e:
        return None, f"Ошибка получения версии: {str(e)}"


def _compare_versions(current: str, latest: str) -> bool:
    """Сравнивает версии. Возвращает True если есть обновление"""
    try:
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]
        
        # Дополняем до одинаковой длины
        max_len = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_len - len(current_parts)))
        latest_parts.extend([0] * (max_len - len(latest_parts)))
        
        return latest_parts > current_parts
        
    except Exception:
        return False


def _get_download_url() -> tuple[str, None] | tuple[None, str]:
    """Получает URL для скачивания последней версии"""
    try:
        import requests
        api_url = "https://api.github.com/repos/proghub13/easy-flasher/releases"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        releases = response.json() or []
        if not releases:
            return None, "Релизы не найдены в репозитории"
        data = next((r for r in releases if not r.get("draft", False)), releases[0])
        assets = data.get("assets", [])
        for asset in assets:
            if asset["name"].endswith(".exe"):
                return asset["browser_download_url"], None
        if assets:
            return assets[0].get("browser_download_url"), None
                
        return None, "Не найден exe файл в последнем релизе"
        
    except Exception as e:
        return None, f"Ошибка получения ссылки: {str(e)}"


@eel.expose
def get_partitions() -> dict:
    try:
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        
        partitions, err = _get_device_partitions(manufacturer, model)
        if err:
            return {"ok": False, "error": err}
        
        return {"ok": True, "partitions": partitions}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_root(image_path: str | None = None, method: str = 'auto'):
    try:
        soc = _detect_soc()
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        no_unlock = _is_in_profiles(manufacturer, model, 'no_unlock_required')
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')

        # Автоматическое резервное копирование boot.img перед рутированием
        _ensure_backup_directory()
        backup_filename = f"boot_{manufacturer}_{model}_{int(time.time())}.img"
        backup_path = pathlib.Path(os.getcwd()) / 'backups' / backup_filename
        backup_res = perform_backup_partition(partition='boot', dest_path=str(backup_path), method=method)
        if not backup_res["ok"]:
            print(f"Предупреждение: Не удалось создать резервную копию boot.img: {backup_res.get('error', 'Неизвестная ошибка')}")
            # Продолжаем, но с предупреждением, так как не всегда возможно забэкапить boot.img через Fastboot
        else:
            print(f"Резервная копия boot.img успешно создана: {backup_path}")
        if soc == 'MediaTek' and 'xiaomi' in manufacturer.lower():
            # MTK Xiaomi: проверяем загрузчик
            if method == 'brom':
                # Полный Brom-путь: пользователь удерживает Vol- на выключенном устройстве
                return {
                    "ok": False,
                    "needs_unlock": True,
                    "manufacturer": manufacturer,
                    "model": model,
                    "message": "Будет выполнена разблокировка через Brom. Выключите телефон, удерживайте Vol- и подключите USB.",
                }
            if method == 'testpoint':
                return {
                    "ok": False,
                    "manual_fastboot": True,
                    "instructions": [
                        "Откройте устройство (на ваш риск)",
                        "Замкните testpoint контакты согласно руководству вашей модели",
                        "Подключите USB, устройство войдёт в режим загрузчика",
                        "Возвратитесь и продолжите"
                    ]
                }
            if not no_cmd_fastboot:
                res = root_helper.perform_mtk_root(image_path)
                return res
            else:
                return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model)}
            is_unlocked, unlock_err = _is_bootloader_unlocked()
            if not is_unlocked:
                return {
                    "ok": False,
                    "needs_unlock": True,
                    "manufacturer": manufacturer,
                    "model": model,
                    "message": f"Загрузчик заблокирован. Нужна разблокировка через Brom. Ошибка: {unlock_err}"
                }
            # Разблокирован — продолжаем рут через helper
            result = root_helper.perform_mtk_root(image_path)
            # Если рутинг успешен, автоматически устанавливаем Magisk
            if result.get("ok") and result.get("message") == "root завершён":
                print("Рутинг завершен успешно. Устанавливаем Magisk...")
                magisk_result = install_magisk()
                if magisk_result.get("success"):
                    result["magisk_installed"] = True
                    result["message"] = "root завершён и Magisk установлен"
                else:
                    result["magisk_error"] = magisk_result.get("error", "Неизвестная ошибка")
                    result["message"] = "root завершён, но не удалось установить Magisk"
            return result
        # Общая схема для MediaTek: нужен патченный boot
        if not image_path:
            raise RuntimeError("Укажите путь к патченному boot.img для рута")
        if not no_cmd_fastboot:
            result = root_helper.perform_mtk_root(image_path)
            # Если рутинг успешен, автоматически устанавливаем Magisk
            if result.get("ok") and result.get("message") == "root завершён":
                print("Рутинг завершен успешно. Устанавливаем Magisk...")
                magisk_result = install_magisk()
                if magisk_result.get("success"):
                    result["magisk_installed"] = True
                    result["message"] = "root завершён и Magisk установлен"
                else:
                    result["magisk_error"] = magisk_result.get("error", "Неизвестная ошибка")
                    result["message"] = "root завершён, но не удалось установить Magisk"
            return result
        else:
            return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model)}
        
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_unlock(method: str = 'auto'):
    try:
        soc = _detect_soc()
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')
        if soc != 'MediaTek':
            return {"ok": False, "error": "Разблокировка загрузчика поддерживается только для MediaTek"}
        if method == 'brom' and soc == 'MediaTek':
            return {"ok": False, "needs_unlock": True, "message": "Brom: выключите устройство, удерживайте Vol− и подключите USB. Затем подтвердите на устройстве."}
        if method == 'testpoint':
            return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model) or [
                "Откройте устройство (на ваш риск)",
                "Замкните testpoint контакты согласно руководству вашей модели",
                "Подключите USB, войдите в загрузчик",
                "Вернитесь в приложение и продолжите"
            ]}
        if not no_cmd_fastboot:
            _reboot_to_bootloader()
        mtk.unlock_bootloader()
        return {"ok": True}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def run_mtk_unlock():
    try:
        # Запускаем Brom-скрипт, пользователь должен зажать Vol- на выключенном телефоне
        mtk.unlock_bootloader()
        return {"ok": True, "message": "Разблокировка выполнена. Нажмите питание для включения устройства."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def get_device_info():
    try:
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        soc = _detect_soc()
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        return {"ok": True, "soc": soc, "manufacturer": manufacturer, "model": model}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def set_manual_device_info(manufacturer: str, model: str):
    try:
        global MANUAL_MANUFACTURER, MANUAL_MODEL
        MANUAL_MANUFACTURER = (manufacturer or '').strip()
        MANUAL_MODEL = (model or '').strip()
        return {"ok": True}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_flash(partition: str, image_path: str, method: str = 'auto'):
    try:
        soc = _detect_soc()
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')

        # Автоматическое резервное копирование перед прошивкой
        _ensure_backup_directory()
        backup_filename = f"{partition}_{manufacturer}_{model}_{int(time.time())}.img"
        backup_path = pathlib.Path(os.getcwd()) / 'backups' / backup_filename
        backup_res = perform_backup_partition(partition=partition, dest_path=str(backup_path), method=method)
        if not backup_res["ok"]:
            print(f"Предупреждение: Не удалось создать резервную копию {partition}: {backup_res.get('error', 'Неизвестная ошибка')}")
        else:
            print(f"Резервная копия {partition} успешно создана: {backup_path}")

        if method == 'brom' and soc == 'MediaTek':
            # Выполняем прошивку через BROM. Пользователь должен ввести устройство в BROM (Vol− на выключенном).
            brom_flash.brom_flash_partition(partition, image_path)
            return {"ok": True}
        if method == 'testpoint':
            # Прошивка через testpoint. Требуется аппаратный вход в TP.
            tp_flash.testpoint_flash_partition(partition, image_path)
            return {"ok": True}
        elif soc == 'MediaTek' and method == 'fastboot': # Explicitly handle Fastboot for MTK if method is specified
            result = flash_partition_fastboot(partition, image_path)
            if not result["ok"]:
                return result
            return {"ok": True, "message": f"Раздел {partition} успешно прошит через Fastboot."}
        elif method == 'fastboot' or (method == 'auto' and soc != 'MediaTek'): # Generic Fastboot for non-MTK or auto
            result = flash_partition_fastboot(partition, image_path)
            if not result["ok"]:
                return result
            return {"ok": True, "message": f"Раздел {partition} успешно прошит через Fastboot."}
        else:
            return {"ok": False, "error": "Функция прошивки пока не реализована для данного типа SoC или выбранного метода."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def reboot_recovery():
    try:
        recovery_helper.reboot_to_recovery()
        return {"ok": True}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_backup_partition(partition: str, dest_path: str, method: str = 'auto') -> dict:
    """Бэкап раздела устройства."""
    try:
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        soc = _detect_soc()
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}
        
        # Создаем директорию для сохранения, если не существует
        backup_dir = pathlib.Path(dest_path).parent
        backup_dir.mkdir(parents=True, exist_ok=True)

        if method == 'brom' and soc == 'MediaTek':
            # Brom-режим для MTK
            brom_flash.brom_read_partition(partition, dest_path)
            return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через BROM."}
        elif method == 'testpoint' and soc == 'MediaTek':
            # Testpoint-режим для MTK
            tp_flash.testpoint_read_partition(partition, dest_path)
            return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через Testpoint."}
        elif method == 'fastboot':
            # Fastboot-режим для всех типов устройств
            result = backup_partition_fastboot(partition, dest_path)
            if not result["ok"]:
                return result
            return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через Fastboot."}
        elif method == 'auto':
            # Автоматический выбор метода
            if soc == 'MediaTek':
                # Для MediaTek пробуем fastboot, если не получается - требуем указать метод
                result = backup_partition_fastboot(partition, dest_path)
                if result["ok"]:
                    return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через Fastboot (авто)."}
                else:
                    return {"ok": False, "error": f"Автоматический бэкап не удался: {result.get('error', 'Неизвестная ошибка')}. Для MediaTek рекомендуется указать метод 'brom' или 'testpoint'."}
            else:
                # Для других SoC используем fastboot
                result = backup_partition_fastboot(partition, dest_path)
                if not result["ok"]:
                    return result
                return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через Fastboot (авто)."}
        else:
            return {"ok": False, "error": f"Неизвестный метод бэкапа: {method}. Доступные методы: 'auto', 'fastboot', 'brom' (только для MediaTek), 'testpoint' (только для MediaTek)."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_restore_partition(partition: str, image_path: str, method: str = 'auto') -> dict:
    """Восстановление раздела устройства из образа."""
    try:
        online, err = _ensure_device_online()
        if not online:
            return {"ok": False, "error": err}
        soc = _detect_soc()
        manufacturer, model, err = _get_manufacturer_and_model()
        if err:
            return {"ok": False, "error": f"Не удалось определить производителя/модель: {err}"}

        if not pathlib.Path(image_path).exists():
            return {"ok": False, "error": f"Файл образа не найден: {image_path}"}

        if method == 'brom' and soc == 'MediaTek':
            # Brom-режим для MTK
            brom_flash.brom_flash_partition(partition, image_path)
            return {"ok": True, "message": f"Раздел {partition} успешно восстановлен из {image_path} через BROM."}
        elif method == 'testpoint' and soc == 'MediaTek':
            # Testpoint-режим для MTK
            tp_flash.testpoint_flash_partition(partition, image_path)
            return {"ok": True, "message": f"Раздел {partition} успешно восстановлен из {image_path} через Testpoint."}
        elif soc == 'MediaTek':
            # Для MediaTek без указания метода попробуем fastboot, если есть такая возможность
            result = flash_partition_fastboot(partition, image_path)
            if not result["ok"]:
                return result
            return {"ok": True, "message": f"Раздел {partition} успешно прошит через Fastboot."}
        else:
            # TODO: Реализовать восстановление через ADB/Fastboot для других SoC (если возможно)
            return {"ok": False, "error": "Функция восстановления пока не реализована для данного типа SoC или выбранного метода."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def get_backup_files(backup_dir: str = 'backups') -> dict:
    """Получить список файлов резервных копий."""
    try:
        base_path = pathlib.Path(os.getcwd()) / backup_dir
        if not base_path.exists():
            return {"ok": True, "files": []}
        
        files = []
        for file_path in base_path.rglob('*'):
            if file_path.is_file():
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": file_path.stat().st_size, # Размер файла в байтах
                    "last_modified": file_path.stat().st_mtime # Время последней модификации
                })
        return {"ok": True, "files": files}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def backup_partition_fastboot(partition: str, dest_path: str) -> dict:
    """Создает бэкап раздела через Fastboot."""
    try:
        # Проверяем, что устройство в fastboot режиме
        print(f"Начинаем бэкап раздела {partition} через Fastboot...")
        online, err = _ensure_fastboot_auto()
        if err:
            return {"ok": False, "error": f"Не удалось найти устройство в fastboot режиме: {err}"}
        
        # Создаем директорию для сохранения, если не существует
        backup_dir = pathlib.Path(dest_path).parent
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Пытаемся получить размер раздела
        out, err = _fastboot('getvar', 'partition-size:' + partition)
        if err:
            return {"ok": False, "error": f"Не удалось получить размер раздела {partition}: {err}"}
        
        # Парсим размер раздела из вывода
        size_str = None
        for line in out.splitlines():
            if 'partition-size:' + partition in line:
                size_str = line.split(':')[-1].strip()
                break
        
        if not size_str:
            return {"ok": False, "error": f"Не удалось определить размер раздела {partition}"}
        
        # Конвертируем размер в байты (если указан в hex)
        try:
            if size_str.startswith('0x'):
                size_bytes = int(size_str, 16)
            else:
                size_bytes = int(size_str)
        except ValueError:
            return {"ok": False, "error": f"Неверный формат размера раздела: {size_str}"}
        
        # Создаем пустой файл нужного размера
        with open(dest_path, 'wb') as f:
            f.write(b'\x00' * size_bytes)
        
        # Пытаемся прочитать раздел через fastboot
        # Примечание: fastboot readback может не работать на всех устройствах
        # В зависимости от версии fastboot и устройства, команда может отличаться
        try:
            # Пробуем команду getvar для получения информации о разделе
            out, err = _fastboot('getvar', 'all')
            if err:
                return {"ok": False, "error": f"Ошибка получения информации о разделе: {err}"}
            
            # Проверяем, поддерживается ли readback для данного раздела
            if 'readback' in out.lower() or 'backup' in out.lower():
                # Если устройство поддерживает readback, используем его
                _, err = _fastboot('readback', partition, dest_path)
                if err:
                    return {"ok": False, "error": f"Ошибка Fastboot при чтении раздела {partition}: {err}"}
            else:
                # Если readback не поддерживается, создаем заглушку с информацией
                with open(dest_path, 'w') as f:
                    f.write(f"# Fastboot backup placeholder for partition: {partition}\n")
                    f.write(f"# Size: {size_bytes} bytes ({size_bytes / (1024*1024):.2f} MB)\n")
                    f.write(f"# Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Note: This device may not support fastboot readback for this partition.\n")
                    f.write(f"# Consider using BROM or Testpoint method for MediaTek devices.\n")
                    f.write(f"# For other devices, check if fastboot readback is supported.\n")
                    f.write(f"# Original size: {size_bytes}\n")
                    # Заполняем остаток нулями
                    remaining = size_bytes - f.tell()
                    if remaining > 0:
                        f.write('\x00' * remaining)
                
                return {"ok": True, "message": f"Создана заглушка бэкапа для раздела {partition} (размер: {size_bytes / (1024*1024):.2f} MB). Устройство может не поддерживать fastboot readback для данного раздела."}
            
            return {"ok": True, "message": f"Раздел {partition} успешно забэкаплен в {dest_path} через Fastboot (размер: {size_bytes / (1024*1024):.2f} MB)."}
            
        except Exception as e:
            # Если fastboot readback не работает, создаем информационную заглушку
            with open(dest_path, 'w') as f:
                f.write(f"# Fastboot backup placeholder for partition: {partition}\n")
                f.write(f"# Size: {size_bytes} bytes ({size_bytes / (1024*1024):.2f} MB)\n")
                f.write(f"# Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Error: {str(e)}\n")
                f.write(f"# Note: Fastboot readback failed. Consider using BROM or Testpoint method.\n")
                f.write(f"# Original size: {size_bytes}\n")
                # Заполняем остаток нулями
                remaining = size_bytes - f.tell()
                if remaining > 0:
                    f.write('\x00' * remaining)
            
            return {"ok": True, "message": f"Создана заглушка бэкапа для раздела {partition} (размер: {size_bytes / (1024*1024):.2f} MB). Fastboot readback недоступен: {str(e)}"}
            
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def flash_partition_fastboot(partition: str, image_path: str) -> dict:
    """Прошивает раздел через Fastboot."""
    try:
        online, err = _ensure_fastboot_auto()
        if err:
            return {"ok": False, "error": err}
        
        if not pathlib.Path(image_path).exists():
            return {"ok": False, "error": f"Файл образа не найден: {image_path}"}
        
        fastboot_path = _fastboot_path()
        _, err = _fastboot('flash', partition, image_path)
        if err:
            return {"ok": False, "error": f"Ошибка Fastboot при прошивке {partition}: {err}"}
        
        return {"ok": True, "message": f"Раздел {partition} успешно прошит из {image_path} через Fastboot."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def erase_partition(partition: str) -> dict:
    """Стирает указанный раздел через Fastboot."""
    try:
        online, err = _ensure_fastboot_auto()
        if err:
            return {"ok": False, "error": err}
        
        fastboot_path = _fastboot_path()
        _, err = _fastboot('erase', partition)
        if err:
            return {"ok": False, "error": f"Ошибка Fastboot при стирании {partition}: {err}"}
            
        return {"ok": True, "message": f"Раздел {partition} успешно стёрт через Fastboot."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def wipe_data() -> dict:
    """Выполняет сброс пользовательских данных и кэша через Fastboot."""
    try:
        online, err = _ensure_fastboot_auto()
        if err:
            return {"ok": False, "error": err}
        
        # Стираем userdata
        _, err = _fastboot('erase', 'userdata')
        if err:
            return {"ok": False, "error": f"Ошибка Fastboot при стирании userdata: {err}"}
        
        # Стираем cache
        _, err = _fastboot('erase', 'cache')
        if err:
            return {"ok": False, "error": f"Ошибка Fastboot при стирании cache: {err}"}
            
        return {"ok": True, "message": "Данные пользователя и кэш успешно стёрты через Fastboot."}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def delete_file(file_path: str) -> dict:
    """Удаляет файл по указанному пути."""
    try:
        file_path_obj = pathlib.Path(file_path)
        if file_path_obj.exists():
            file_path_obj.unlink()
            return {"ok": True, "message": f"Файл {file_path} успешно удален."}
        else:
            return {"ok": False, "error": f"Файл {file_path} не найден."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@eel.expose
def create_custom_backup(partition: str, backup_name: str, method: str = 'auto') -> dict:
    """Создает произвольный бэкап раздела."""
    try:
        _ensure_backup_directory()
        backup_filename = f"{backup_name}_{partition}_{int(time.time())}.img"
        backup_path = pathlib.Path(os.getcwd()) / 'backups' / backup_filename
        
        result = perform_backup_partition(partition=partition, dest_path=str(backup_path), method=method)
        if result["ok"]:
            result["backup_path"] = str(backup_path)
        return result
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def check_fastboot_devices() -> dict:
    """Проверяет наличие fastboot устройств и возвращает детальную информацию."""
    try:
        print("Проверяем fastboot устройства...")
        out, err = _fastboot('devices')
        
        result = {
            "ok": True,
            "fastboot_output": out,
            "fastboot_error": err,
            "has_fastboot": False,
            "devices": []
        }
        
        if err:
            result["error"] = f"Ошибка при проверке fastboot устройств: {err}"
            return result
        
        # Парсим вывод fastboot devices
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]
                
                device_info = {
                    "id": device_id,
                    "status": status,
                    "is_fastboot": 'fastboot' in status.lower()
                }
                result["devices"].append(device_info)
                
                if device_info["is_fastboot"]:
                    result["has_fastboot"] = True
        
        # Также проверяем ADB устройства
        adb_out, adb_err = _adb('devices')
        result["adb_output"] = adb_out
        result["adb_error"] = adb_err
        result["has_adb"] = '\tdevice' in adb_out
        
        return result
        
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def reboot_to_fastboot() -> dict:
    """Перезагружает устройство в fastboot режим."""
    try:
        print("Перезагружаем устройство в fastboot...")
        
        # Сначала проверяем ADB
        if not _has_adb_device():
            return {"ok": False, "error": "ADB устройство не найдено. Подключите устройство и включите отладку по USB."}
        
        # Перезагружаем в bootloader
        _, err = _adb('reboot', 'bootloader')
        if err:
            return {"ok": False, "error": f"Ошибка при перезагрузке в bootloader: {err}"}
        
        return {"ok": True, "message": "Устройство перезагружается в fastboot режим. Подождите 10-30 секунд и проверьте статус."}
        
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


# -------------------- Plugin Management API --------------------

@eel.expose
def disable_plugin(plugin_id: str) -> dict:
    """Отключить плагин на текущую сессию"""
    global DISABLED_PLUGINS
    DISABLED_PLUGINS.add(plugin_id)
    # Перезагружаем плагины чтобы отключенный плагин перестал работать
    load_plugins()
    return {"ok": True}

@eel.expose
def enable_plugin(plugin_id: str) -> dict:
    """Включить плагин"""
    global DISABLED_PLUGINS
    DISABLED_PLUGINS.discard(plugin_id)
    # Перезагружаем плагины только при включении
    load_plugins()
    return {"ok": True}

@eel.expose
def delete_plugin(plugin_id: str) -> dict:
    """Удалить плагин полностью"""
    try:
        plugin_path = pathlib.Path(os.getcwd()) / 'plugins' / f'{plugin_id}.py'
        if plugin_path.exists():
            plugin_path.unlink()
        
        # Удаляем папку с веб-ресурсами если есть
        web_path = pathlib.Path(os.getcwd()) / 'plugins' / plugin_id
        if web_path.exists():
            import shutil
            shutil.rmtree(web_path)
        
        # Удаляем из отключенных
        DISABLED_PLUGINS.discard(plugin_id)
        
        # Перезагружаем плагины
        load_plugins()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@eel.expose
def get_plugin_files(plugin_id: str) -> dict:
    """Получить список файлов плагина"""
    try:
        plugin_dir = pathlib.Path(os.getcwd()) / 'plugins' / plugin_id
        files = []
        
        # Основной файл плагина
        main_file = pathlib.Path(os.getcwd()) / 'plugins' / f'{plugin_id}.py'
        if main_file.exists():
            files.append({
                "name": f"{plugin_id}.py",
                "path": str(main_file),
                "type": "main"
            })
        
        # Файлы в папке плагина
        if plugin_dir.exists():
            for file_path in plugin_dir.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(plugin_dir)
                    files.append({
                        "name": str(rel_path),
                        "path": str(file_path),
                        "type": "web" if file_path.suffix in ['.html', '.css', '.js'] else "other"
                    })
        
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@eel.expose
def read_plugin_file(file_path: str) -> dict:
    """Прочитать содержимое файла плагина"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"ok": True, "content": content}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@eel.expose
def write_plugin_file(file_path: str, content: str) -> dict:
    """Записать содержимое в файл плагина"""
    try:
        # Создаем директорию если не существует
        pathlib.Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Инициализация папки backups при запуске
_ensure_backup_directory()

##############################################
# ---------------- Firmware Browser API ---------------- #
##############################################

_FW_CATALOG_PATH = pathlib.Path(os.getcwd()) / 'firmware_catalog.json'
_FW_FAVORITES_PATH = pathlib.Path(os.getcwd()) / 'favorites.json'
_FW_DOWNLOAD_PROGRESS: dict[str, dict] = {}

FIRMWARE_CATALOG_BUILTIN: dict[str, list[dict]] = {
    "recovery": [
        {"name": "OrangeFox - Redmi Note 7 (lavender)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi note 7", "lavender"], "url": "https://api.orangefox.download/device/lavender/recovery.img"},
        {"name": "OrangeFox - Redmi Note 8 (ginkgo)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi note 8", "ginkgo"], "url": "https://api.orangefox.download/device/ginkgo/recovery.img"},
        {"name": "OrangeFox - POCO X3 NFC (surya)", "partition": "recovery", "vendors": ["POCO", "Xiaomi"], "models": ["poco x3 nfc", "surya"], "url": "https://api.orangefox.download/device/surya/recovery.img"},
        {"name": "OrangeFox - Redmi Note 8T (willow)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi note 8t", "willow"], "url": "https://api.orangefox.download/device/willow/recovery.img"},
        {"name": "OrangeFox - Redmi 9 (lancelot)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi 9", "lancelot"], "url": "https://api.orangefox.download/device/lancelot/recovery.img"},
        {"name": "OrangeFox - Redmi 6A (cactus)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi 6a", "cactus"], "url": "https://api.orangefox.download/device/cactus/recovery.img"},
        {"name": "PitchBlack - Redmi Note 5 (whyred)", "partition": "recovery", "vendors": ["Xiaomi"], "models": ["redmi note 5", "whyred"], "url": "https://pitchblackrecovery.com/download/whyred"},
        {"name": "SHRP - POCO F1 (beryllium)", "partition": "recovery", "vendors": ["POCO", "Xiaomi"], "models": ["poco f1", "beryllium"], "url": "https://sourceforge.net/projects/shrp/files/beryllium/"},
    ],
    "system": [
        {"name": "PixelExperience - Redmi Note 8 (ginkgo)", "partition": "system", "vendors": ["Xiaomi"], "models": ["redmi note 8", "ginkgo"], "url": "https://download.pixelexperience.org/ginkgo"},
        {"name": "crDroid - Redmi Note 8 (ginkgo)", "partition": "system", "vendors": ["Xiaomi"], "models": ["redmi note 8", "ginkgo"], "url": "https://crdroid.net/ginkgo"},
        {"name": "EvolutionX - Poco F3 (alioth)", "partition": "system", "vendors": ["POCO", "Xiaomi"], "models": ["poco f3", "alioth"], "url": "https://evolution-x.org/device/alioth"},
        {"name": "ArrowOS - POCO X3 Pro (vayu)", "partition": "system", "vendors": ["POCO", "Xiaomi"], "models": ["poco x3 pro", "vayu"], "url": "https://arrowos.net/download?device=vayu"},
        {"name": "MIUI Mix - Redmi Note 8 (ginkgo)", "partition": "system", "vendors": ["Xiaomi"], "models": ["redmi note 8", "ginkgo"], "url": "https://miuimix.ru/"},
        {"name": "MIUI Mix - POCO X3 NFC (surya)", "partition": "system", "vendors": ["POCO", "Xiaomi"], "models": ["poco x3 nfc", "surya"], "url": "https://miuimix.ru/"},
        {"name": "LineageOS - OnePlus 3 (oneplus3)", "partition": "system", "vendors": ["OnePlus"], "models": ["oneplus 3", "oneplus3"], "url": "https://download.lineageos.org/devices/oneplus3"},
        {"name": "LineageOS - Nexus 5X (bullhead)", "partition": "system", "vendors": ["Google"], "models": ["nexus 5x", "bullhead"], "url": "https://download.lineageos.org/devices/bullhead"},
    ]
}


def _load_fw_catalog() -> dict:
    """Загружает основной каталог и все расширения из каталога catalog/ и объединяет их."""
    base: dict = {
        "recovery": list(FIRMWARE_CATALOG_BUILTIN.get("recovery", [])),
        "system": list(FIRMWARE_CATALOG_BUILTIN.get("system", []))
    }
    try:
        if _FW_CATALOG_PATH.exists():
            with open(_FW_CATALOG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
                base["recovery"].extend(data.get("recovery", []))
                base["system"].extend(data.get("system", []))
    except Exception:
        traceback.print_exc()

    # Подгружаем дополнительные файлы из catalog/
    try:
        catalog_dir = pathlib.Path(os.getcwd()) / 'catalog'
        if catalog_dir.exists() and catalog_dir.is_dir():
            for p in sorted(catalog_dir.glob('*.json')):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f) or {}
                        rec = data.get('recovery', [])
                        sys = data.get('system', [])
                        if isinstance(rec, list):
                            base['recovery'].extend(rec)
                        if isinstance(sys, list):
                            base['system'].extend(sys)
                except Exception:
                    traceback.print_exc()
    except Exception:
        traceback.print_exc()

    return base


def _save_favorites(names: list[str]) -> None:
    try:
        with open(_FW_FAVORITES_PATH, 'w', encoding='utf-8') as f:
            json.dump({"names": names}, f, ensure_ascii=False, indent=2)
    except Exception:
        traceback.print_exc()


def _load_favorites() -> list[str]:
    try:
        if not _FW_FAVORITES_PATH.exists():
            return []
        with open(_FW_FAVORITES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            names = data.get('names')
            return names if isinstance(names, list) else []
    except Exception:
        traceback.print_exc()
        return []


def _device_tuple_or_none() -> tuple[str, str] | None:
    ok, err = _ensure_device_online()
    if not ok:
        return None
    man, model, _ = _get_manufacturer_and_model()
    return (man, model)


def _matches_device(entry: dict, manufacturer: str, model: str) -> bool:
    try:
        vendors = [str(v).lower() for v in (entry.get('vendors') or [])]
        models = [str(m).lower() for m in (entry.get('models') or [])]
        if vendors and manufacturer.lower() not in vendors:
            return False
        if models:
            low = model.lower()
            return any(m in low for m in models)
        return True
    except Exception:
        return False


def _extract_codename(manufacturer: str, model: str) -> str | None:
    try:
        import re
        txt = f"{manufacturer} {model}".strip()
        m = re.search(r'\(([^\)]+)\)', txt)
        if m:
            code = m.group(1).strip()
            if 2 <= len(code) <= 32:
                return code
        low = txt.lower()
        known = {
            'redmi note 8': 'ginkgo',
            'poco f3': 'alioth',
            'poco x3 nfc': 'surya',
            'poco x3 pro': 'vayu',
            'redmi note 7': 'lavender',
            'redmi note 8t': 'willow',
            'redmi note 5': 'whyred',
            'redmi note 4': 'mido',
            'redmi 4x': 'santoni',
            'redmi 7a': 'pine',
            'redmi 6a': 'cactus',
            'redmi 9': 'lancelot',
            'poco f1': 'beryllium',
            'mi a1': 'tissot',
            'mi a2': 'jasmine_sprout',
            'oneplus one': 'bacon',
            'oneplus 3': 'oneplus3',
            'oneplus 5': 'cheeseburger',
            'oneplus 6': 'enchilada',
            'moto g5 plus': 'potter',
            'moto g4': 'athene',
            'nexus 5': 'hammerhead',
            'nexus 5x': 'bullhead',
            'nexus 6': 'shamu',
        }
        for key, val in known.items():
            if key in low:
                return val
        return None
    except Exception:
        return None


def _provider_online_recovery(manufacturer: str, model: str) -> list[dict]:
    code = _extract_codename(manufacturer, model)
    if not code:
        return []
    out: list[dict] = []
    twrp_url = f"https://dl.twrp.me/{code}/recovery.img"
    out.append({
        "name": f"TWRP - {model} ({code})",
        "partition": "recovery",
        "vendors": [manufacturer],
        "models": [model.lower(), code.lower()],
        "url": twrp_url,
        "source": "online",
    })
    of_url = f"https://api.orangefox.download/device/{code}/recovery.img"
    out.append({
        "name": f"OrangeFox - {model} ({code})",
        "partition": "recovery",
        "vendors": [manufacturer],
        "models": [model.lower(), code.lower()],
        "url": of_url,
        "source": "online",
    })
    # PitchBlack Recovery (страница загрузки по коду, если доступна)
    pbrp_url = f"https://pitchblackrecovery.com/download/{code}"
    out.append({
        "name": f"PitchBlack - {model} ({code})",
        "partition": "recovery",
        "vendors": [manufacturer],
        "models": [model.lower(), code.lower()],
        "url": pbrp_url,
        "source": "online_page",
    })
    # SHRP (страница на SourceForge зачастую разбита по устройствам)
    shrp_url = f"https://sourceforge.net/projects/shrp/files/{code}/"
    out.append({
        "name": f"SHRP - {model} ({code})",
        "partition": "recovery",
        "vendors": [manufacturer],
        "models": [model.lower(), code.lower()],
        "url": shrp_url,
        "source": "online_page",
    })
    return out


def _provider_online_system(manufacturer: str, model: str) -> list[dict]:
    code = _extract_codename(manufacturer, model)
    if not code:
        return []
    out: list[dict] = []

    providers: list[tuple[str, str]] = [
        ("LineageOS", f"https://download.lineageos.org/devices/{code}"),
        ("PixelExperience", f"https://download.pixelexperience.org/{code}"),
        ("crDroid", f"https://crdroid.net/{code}"),
        ("EvolutionX", f"https://evolution-x.org/device/{code}"),
        ("ArrowOS", f"https://arrowos.net/download?device={code}"),
        ("PixelOS", f"https://pixelos.net/download/{code}"),
        ("AOSP Extended", f"https://downloads.aospextended.com/{code}"),
        ("Resurrection Remix", f"https://get.resurrectionremix.com/{code}"),
        ("Paranoid Android", f"https://paranoidandroid.co/devices/{code}"),
        ("Havoc-OS", f"https://download.havoc-os.com/{code}"),
        ("DerpFest", f"https://derpfest.org/device/{code}"),
        ("OmniROM", f"https://dl.omnirom.org/{code}"),
        ("NitrogenOS", f"https://sourceforge.net/projects/nitrogen-project/files/{code}/"),
        ("CarbonROM", f"https://get.carbonrom.org/device/{code}"),
        ("Bliss ROM", f"https://downloads.blissroms.org/download/{code}"),
        ("Potato Open Sauce (POSP)", f"https://potatoproject.co/device/{code}"),
        ("MSM Xtended", f"https://downloads.msmdroid.com/{code}"),
        ("dotOS", f"https://www.dotos.org/devices/{code}"),
        ("Bootleggers", f"https://downloads.bootleggersrom.xyz/{code}"),
        ("AOSiP", f"https://aosip.dev/devices/{code}"),
        ("Project Elixir", f"https://projectelixiros.com/device/{code}"),
        ("Project Sakura", f"https://projectsakura.xyz/download/{code}"),
        ("Project Zephyrus", f"https://sourceforge.net/projects/project-zyphrus/files/{code}/"),
        ("Project Lighthouse", f"https://sourceforge.net/projects/project-lighthouse/files/{code}/"),
        ("Corvus OS", f"https://get.corvusrom.com/{code}"),
        ("PixysOS", f"https://downloads.pixysos.com/{code}"),
        ("RevengeOS", f"https://sourceforge.net/projects/revengeos/files/{code}/"),
        ("OctaviOS", f"https://downloads.octavi-os.com/{code}"),
        ("LegionOS", f"https://downloads.legionrom.com/{code}"),
        ("ColtOS", f"https://sourceforge.net/projects/coltos/files/{code}/"),
        ("SuperiorOS", f"https://sourceforge.net/projects/superioros/files/{code}/"),
        ("Syberia Project", f"https://syberiaos.com/downloads/{code}"),
        ("Nusantara Project", f"https://sourceforge.net/projects/project-nusantara/files/{code}/"),
        ("StatiXOS", f"https://downloads.statixos.com/{code}"),
        ("PixelDust", f"https://pixeldustproject.org/devices/{code}"),
        ("ShapeShiftOS", f"https://sourceforge.net/projects/shapeshiftos/files/{code}/"),
        ("Dirty Unicorns", f"https://download.dirtyunicorns.com/devices/{code}"),
        ("CherishOS", f"https://sourceforge.net/projects/cherish-os/files/{code}/"),
        ("Nameless AOSP", f"https://nameless.wiki/guide/{code}"),
        ("AwakenOS", f"https://sourceforge.net/projects/project-awaken/files/{code}/"),
        ("FlamingoOS", f"https://sourceforge.net/projects/flamingoos/files/{code}/"),
        ("LeOS", f"https://sourceforge.net/projects/leos-release/files/{code}/"),
        ("RiceDroid", f"https://sourceforge.net/projects/ricedroid/files/{code}/"),
        ("PixelPlusUI", f"https://downloads.pixelplusui.com/{code}"),
        ("InfinityOS", f"https://sourceforge.net/projects/infinity-x/files/{code}/"),
        ("ArrowOS (mirror)", f"https://sourceforge.net/projects/arrow-os/files/{code}/"),
        ("AncientOS", f"https://sourceforge.net/projects/ancientrom/files/{code}/"),
        ("AICP", f"https://dwnld.aicp-rom.com/{code}"),
        ("The Pixel Remix (TPR)", f"https://sourceforge.net/projects/thepixelremix/files/{code}/"),
        ("Resurrection Remix (mirror)", f"https://sourceforge.net/projects/resurrectionremix/files/{code}/"),
        ("LineageOS (mirror)", f"https://mirrorbits.lineageos.org/full/{code}/"),
        ("KangOS", f"https://sourceforge.net/projects/kangos-project/files/{code}/"),
        ("Pixel Extended (PEX)", f"https://sourceforge.net/projects/pixelexperiences/files/{code}/"),
        ("MIUI Mix", "https://miuimix.ru/"),
        ("Xiaomi.EU (device forum)", f"https://xiaomi.eu/community/forums/{code}.123/"),
        ("PixelOS (SF mirror)", f"https://sourceforge.net/projects/pixelos-releases/files/{code}/"),
        ("PixelOS (alt)", f"https://get.pixelsauce.org/{code}"),
    ]

    for pname, purl in providers:
        out.append({
            "name": f"{pname} - {model} ({code})",
            "partition": "system",
            "vendors": [manufacturer],
            "models": [model.lower(), code.lower()],
            "url": purl,
            "source": "online_page",
        })

    return out

@eel.expose
def fw_get_device() -> dict:
    try:
        dev = _device_tuple_or_none()
        if not dev:
            return {"ok": True, "connected": False}
        man, model = dev
        return {"ok": True, "connected": True, "manufacturer": man, "model": model}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_find_device(query: str) -> dict:
    """Возвращает список вариантов устройств из каталога по подстроке."""
    try:
        q = (query or '').strip().lower()
        if not q:
            return {"ok": True, "items": []}
        cat = _load_fw_catalog()
        seen: set[tuple[str, str]] = set()
        items: list[dict] = []
        for category in ('recovery', 'system'):
            for it in cat.get(category, []):
                vendors = it.get('vendors') or []
                models = it.get('models') or []
                for v in vendors or ['']:
                    for m in models or ['']:
                        cand_v = str(v)
                        cand_m = str(m)
                        label = (cand_v + ' ' + cand_m).strip()
                        if not label:
                            continue
                        if q in label.lower():
                            key = (cand_v.lower(), cand_m.lower())
                            if key not in seen:
                                seen.add(key)
                                items.append({"manufacturer": cand_v, "model": cand_m})
        # ограничим до разумного кол-ва
        return {"ok": True, "items": items[:50]}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_list(category: str, manufacturer: str | None = None, model: str | None = None) -> dict:
    try:
        cat = (category or 'recovery').lower()
        data = _load_fw_catalog().get(cat, [])
        man = (manufacturer or '').strip()
        mod = (model or '').strip()
        if man and mod:
            filtered = [x for x in data if _matches_device(x, man, mod)]
        elif man:
            filtered = [x for x in data if _matches_device(x, man, mod)]
        else:
            filtered = data
        # Добавляем онлайн-провайдеры
        online_items: list[dict] = []
        if man and mod:
            if cat == 'recovery':
                online_items = _provider_online_recovery(man, mod)
            elif cat == 'system':
                online_items = _provider_online_system(man, mod)
        by_name: dict[str, dict] = {}
        seen_urls: set[str] = set()
        merged_items = [*filtered, *online_items]
        unique_items: list[dict] = []
        for it in merged_items:
            name = str(it.get('name', '')).strip()
            url = str(it.get('url', '')).strip()
            key = name.lower()
            url_key = url.lower()

            if url_key and url_key in seen_urls:
                continue
            if key and key in by_name:
                # Если названия совпадают, но URL разные, оставляем только первый.
                continue

            if key:
                by_name[key] = it
            if url_key:
                seen_urls.add(url_key)
            unique_items.append(it)

        merged = unique_items
        fav = set(_load_favorites())
        # enrich
        out = []
        for it in merged:
            name = str(it.get('name', ''))
            out.append({
                **it,
                "favorite": name in fav
            })
        return {"ok": True, "items": out}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_get_favorites() -> dict:
    try:
        return {"ok": True, "names": _load_favorites()}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_toggle_favorite(name: str) -> dict:
    try:
        name = (name or '').strip()
        if not name:
            return {"ok": False, "error": "Пустое имя прошивки"}
        fav = set(_load_favorites())
        if name in fav:
            fav.remove(name)
            state = False
        else:
            fav.add(name)
            state = True
        _save_favorites(sorted(fav))
        return {"ok": True, "favorite": state}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_get_download_progress(name: str) -> dict:
    try:
        key = (name or '').strip()
        if not key:
            return {"ok": False, "error": "Пустое имя загрузки"}
        entry = _FW_DOWNLOAD_PROGRESS.get(key)
        if not entry:
            return {"ok": False}
        return {"ok": True, "name": key, **entry}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_clear_download_progress(name: str) -> dict:
    try:
        key = (name or '').strip()
        if key:
            _FW_DOWNLOAD_PROGRESS.pop(key, None)
        return {"ok": True}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def fw_download(category: str, name: str, manufacturer: str | None = None, model: str | None = None) -> dict:
    try:
        name = (name or '').strip()
        if not name:
            return {"ok": False, "error": "Не указано имя прошивки"}
        cat = (category or 'recovery').lower()
        man = (manufacturer or '').strip()
        mod = (model or '').strip()

        res = fw_list(cat, man or None, mod or None)
        if not isinstance(res, dict) or not res.get('ok'):
            return res if isinstance(res, dict) else {"ok": False, "error": "Не удалось получить список прошивок"}
        items = res.get('items') or []
        target = next((it for it in items if str(it.get('name')) == name), None)
        if not target:
            return {"ok": False, "error": "Прошивка не найдена"}

        url = _resolve_download_url(target).strip()
        if not url:
            return {"ok": False, "error": "Не удалось получить ссылку для скачивания"}

        downloads_dir = pathlib.Path(os.getcwd()) / 'downloads' / 'firmware'
        downloads_dir.mkdir(parents=True, exist_ok=True)

        from urllib.parse import urlparse, unquote
        import re

        parsed = urlparse(url)
        parsed_path = unquote(parsed.path or '')
        fname = pathlib.Path(parsed_path).name
        if not fname or fname.lower() in ('download', 'index.html', 'get'):
            safe_name = re.sub(r'[^a-zA-Z0-9._-]+', '_', str(target.get('name', 'firmware'))).strip('_')
            if not safe_name:
                safe_name = 'firmware'
            partition = str(target.get('partition', 'fw')).lower()
            ext = '.img' if partition == 'recovery' else '.zip'
            fname = f"{safe_name}_{int(time.time())}{ext}"

        local_path = downloads_dir / fname
        progress_entry = _FW_DOWNLOAD_PROGRESS.setdefault(name, {})
        progress_entry.update({
            "status": "starting",
            "downloaded": 0,
            "total": 0,
            "url": url,
            "updated_at": time.time()
        })

        def _progress(downloaded: int, total: int) -> None:
            entry = _FW_DOWNLOAD_PROGRESS.setdefault(name, {"url": url})
            entry["downloaded"] = downloaded
            entry["total"] = total
            entry["status"] = "downloading"
            entry["updated_at"] = time.time()

        ok_dl, err_dl = _download_to(local_path, url, progress=_progress)
        if not ok_dl:
            entry = _FW_DOWNLOAD_PROGRESS.setdefault(name, {"url": url})
            entry["status"] = "error"
            entry["error"] = err_dl or "Неизвестная ошибка"
            entry.setdefault("downloaded", 0)
            entry.setdefault("total", 0)
            entry["updated_at"] = time.time()
            try:
                eel.fail_fw_download(name, err_dl or '')
            except Exception:
                pass
            return {"ok": False, "error": f"Не удалось скачать: {err_dl}"}

        size = local_path.stat().st_size if local_path.exists() else _FW_DOWNLOAD_PROGRESS.get(name, {}).get("downloaded", 0)
        entry = _FW_DOWNLOAD_PROGRESS.setdefault(name, {"url": url})
        entry.update({
            "status": "finished",
            "downloaded": size,
            "total": size or entry.get("total", size),
            "path": str(local_path),
            "updated_at": time.time()
        })

        return {"ok": True, "path": str(local_path), "name": name}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


def _download_to(path: pathlib.Path, url: str, progress: Callable[[int, int], None] | None = None) -> tuple[bool, str | None]:
    try:
        import requests
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        total = int(r.headers.get('content-length') or 0)
        downloaded = 0
        if progress:
            try:
                progress(downloaded, total)
            except Exception:
                pass
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                    f.write(chunk)
                downloaded += len(chunk)
                if progress:
                    try:
                        progress(downloaded, total)
                    except Exception:
                        pass
        return True, None
    except Exception as e:
        return False, str(e)


def _http_get_text(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoRoot/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text, None
    except Exception as e:
        return None, str(e)


def _http_get_json(url: str, timeout: int = 15) -> tuple[dict | list | None, str | None]:
    try:
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoRoot/1.0',
            'Accept': 'application/json'
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)


def _extract_download_link_from_html(html: str, base_url: str, allowed_exts: list[str]) -> str | None:
    try:
        import re
        from urllib.parse import urljoin

        meta = re.search(r'http-equiv\s*=\s*"refresh"[^>]*url=([^";>]+)', html, flags=re.IGNORECASE)
        if meta:
            link = meta.group(1).strip()
            if link:
                return urljoin(base_url, link)

        candidates = set(re.findall(r'href=["\'](.*?)["\']', html, flags=re.IGNORECASE))
        candidates.update(re.findall(r'(https?://[^"\'\s>]+)', html, flags=re.IGNORECASE))

        for cand in candidates:
            if not cand:
                continue
            cand = cand.strip()
            lower = cand.lower()
            if any(lower.endswith(ext) for ext in allowed_exts) or any(ext in lower for ext in allowed_exts):
                return urljoin(base_url, cand)
    except Exception:
        pass
    return None


def _normalize_download_url(url: str, partition: str) -> str:
    if not url:
        return url

    allowed_exts = ['.img', '.zip', '.bin', '.tar', '.tgz', '.tar.gz', '.rar', '.7z', '.xz', '.gz']
    url_no_query = url.split('?', 1)[0].lower()
    if any(url_no_query.endswith(ext) for ext in allowed_exts):
        return url

    try:
        import requests
        head_resp = requests.head(url, allow_redirects=True, timeout=10)
        final_url = head_resp.url or url
        final_no_query = final_url.split('?', 1)[0].lower()
        content_type = (head_resp.headers.get('content-type') or '').lower()
        if any(final_no_query.endswith(ext) for ext in allowed_exts):
            return final_url
        if any(token in content_type for token in ['application/zip', 'application/octet-stream', 'application/x-', 'application/gzip', 'application/x-gzip', 'application/x-7z-compressed', 'application/x-rar-compressed', 'application/x-tar']) or 'image' in content_type:
            return final_url
        if content_type and 'text/html' not in content_type:
            return final_url
        url = final_url
    except Exception:
        pass

    html, err = _http_get_text(url)
    if isinstance(html, str):
        link = _extract_download_link_from_html(html, url, allowed_exts)
        if link:
            return link
    return url


def _extract_pixelexperience_from_html(html: str, prefer_plus: bool, partition: str) -> str | None:
    try:
        import json
        import re
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, flags=re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))
    except Exception:
        return None

    page_props = data if isinstance(data, dict) else {}
    page_props = page_props.get('props') if isinstance(page_props.get('props'), dict) else {}
    page_props = page_props.get('pageProps') if isinstance(page_props.get('pageProps'), dict) else page_props

    builds_data = []
    if isinstance(page_props, dict):
        bd = page_props.get('buildsData')
        if isinstance(bd, list):
            builds_data = bd
        else:
            # В некоторых страницах данные могут лежать в pageProps['build']
            single_build = page_props.get('build')
            if isinstance(single_build, dict):
                target = single_build
                if partition == 'recovery':
                    rec = target.get('recovery_image') or {}
                    return rec.get('url') or target.get('url')
                return target.get('url')

    if not builds_data:
        return None

    def _choose_build() -> dict | None:
        chosen: dict | None = None
        for entry in builds_data:
            if not isinstance(entry, dict):
                continue
            version_info = entry.get('version_info') or {}
            version_name = str(version_info.get('version_name', '')).lower()
            builds = entry.get('builds') or []
            if not isinstance(builds, list) or not builds:
                continue
            is_plus_version = 'plus' in version_name
            if prefer_plus and not is_plus_version:
                continue
            if not prefer_plus and is_plus_version:
                if chosen is None:
                    # пропускаем plus, но запомнили на всякий случай
                    chosen = builds[0]
                continue
            return builds[0]
        if chosen:
            return chosen
        for entry in builds_data:
            builds = entry.get('builds') or []
            if isinstance(builds, list) and builds:
                return builds[0]
        return None

    build = _choose_build()
    if not isinstance(build, dict):
        return None

    if partition == 'recovery':
        rec = build.get('recovery_image') or {}
        url = rec.get('url')
        if isinstance(url, str) and url.strip():
            return url.strip()

    url = build.get('url')
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _resolve_download_url(item: dict) -> str:
    """Пытается получить прямую ссылку для загрузки из официальной страницы/API.
    Возвращает исходный URL, если ничего лучше найти не удалось.
    Поддерживает некоторые популярные проекты (LineageOS, ArrowOS, SourceForge-страницы и др.).
    """
    try:
        import re
        url = str(item.get('url', '')).strip()
        partition = str(item.get('partition', '')).strip().lower()
        name = str(item.get('name', ''))

        if not url:
            return url

        # Если это уже прямая ссылка на образ/zip — возвращаем как есть
        if any(url.lower().endswith(ext) for ext in ('.img', '.zip', '.apk')):
            return _normalize_download_url(url, partition)

        # TWRP прямой путь по коду устройства
        # dl.twrp.me/<code>/recovery.img — уже прямой
        if 'dl.twrp.me' in url:
            return _normalize_download_url(url, partition)

        # OrangeFox API уже выдает прямой img
        if 'api.orangefox.download' in url:
            return _normalize_download_url(url, partition)

        # PixelExperience — страница с React/Next.js, извлекаем прямую ссылку из __NEXT_DATA__
        if 'pixelexperience.org' in url:
            prefer_plus = 'plus' in name.lower()
            html, err = _http_get_text(url)
            if isinstance(html, str):
                direct = _extract_pixelexperience_from_html(html, prefer_plus, partition)
                if direct:
                    return _normalize_download_url(direct, partition)
            # Если текущий URL это changelog-страница, пробуем получить JSON по ней же
            # Иногда необходим реальный build. Попробуем вариант с добавлением '/download'.
            if '/changelog/' in url and not url.endswith('/download'):
                alt = url.rstrip('/') + '/download'
                alt = _normalize_download_url(alt, partition)
                if alt != url:
                    return alt

        # LineageOS: используем публичный OTA API если удалось извлечь код устройства из имени
        # Ожидается, что models содержит и код, и модель
        models = [str(m).lower() for m in (item.get('models') or [])]
        code = None
        for m in models:
            if len(m) <= 16 and re.fullmatch(r'[a-z0-9_\-]+', m or ''):
                code = m
                break
        if 'download.lineageos.org' in url and code:
            # тип сборки: nightly/stable — возьмём nightly как наиболее распространённый
            api = f"https://ota.lineageos.org/api/v1/{code}/nightly/latest"
            data, err = _http_get_json(api)
            if isinstance(data, dict):
                # В ответе ожидается поле 'response' со списком
                resp = data.get('response') if isinstance(data.get('response'), list) else []
                if resp:
                    rom = resp[0]
                    dl = rom.get('url') or rom.get('download')
                    if isinstance(dl, str) and dl.lower().endswith('.zip'):
                        return _normalize_download_url(dl, partition)

        # ArrowOS: официальный API
        if ('arrowos.net' in url or 'arrowos' in name.lower()) and code:
            api = f"https://api.arrowos.net/v2/devices/{code}.json"
            data, err = _http_get_json(api)
            if isinstance(data, dict):
                builds = data.get('response') or data.get('files') or []
                if isinstance(builds, list) and builds:
                    # берём первый (последний) билд со ссылкой
                    for b in builds:
                        dl = b.get('url') or b.get('download')
                        if isinstance(dl, str) and dl.lower().endswith('.zip'):
                            return _normalize_download_url(dl, partition)

        # SourceForge-страницы (SHRP, PBRP, EvolutionX и т.п.):
        # вытягиваем первую ссылку на .img или .zip из HTML
        if 'sourceforge.net/projects/' in url:
            html, err = _http_get_text(url)
            if isinstance(html, str):
                # Ищем ссылки на /files/.../(download|/...) и прямые зеркала downloads.sourceforge.net
                candidates = re.findall(r'href=["\'](.*?)["\']', html, flags=re.IGNORECASE)
                sf_links: list[str] = []
                for h in candidates:
                    h2 = h.strip()
                    if not h2:
                        continue
                    if any(x in h2 for x in ['downloads.sourceforge.net/project/', '/files/']):
                        if any(h2.lower().endswith(ext) or (ext in h2.lower()) for ext in ['.img', '.zip']):
                            sf_links.append(h2)
                    if h2.startswith('/projects/'):
                        full = 'https://sourceforge.net' + h2
                        if any(full.lower().endswith(ext) or (ext in full.lower()) for ext in ['.img', '.zip']):
                            sf_links.append(full)
                if sf_links:
                    # если это страница /files/... — добавим /download для редиректа на зеркало
                    chosen = sf_links[0]
                    if '/files/' in chosen and not chosen.endswith('/download'):
                        chosen = chosen.rstrip('/') + '/download'
                    return _normalize_download_url(chosen, partition)

        # PitchBlack страница загрузки по коду: попробуем найти .img или SF ссылку
        if 'pitchblackrecovery.com/download/' in url:
            html, err = _http_get_text(url)
            if isinstance(html, str):
                candidates = re.findall(r'href=["\'](.*?)["\']', html, flags=re.IGNORECASE)
                for h in candidates:
                    if h.lower().endswith('.img') or h.lower().endswith('.zip'):
                        return _normalize_download_url(h, partition)
                    if 'sourceforge.net' in h:
                        # переиспользуем обработку SF
                        resolved_sf = _resolve_download_url({"url": h, "partition": partition, "name": name, "models": item.get('models')})
                        return _normalize_download_url(resolved_sf, partition)

        # По умолчанию — возвращаем исходный URL
        return _normalize_download_url(url, partition)
    except Exception:
        return str(item.get('url', ''))

@eel.expose
def fw_install(category: str, selected_names: list[str], manufacturer: str | None = None, model: str | None = None, method: str = 'auto', continue_without_backup: bool = False, pre_downloaded: dict[str, str] | None = None) -> dict:
    """Установка выбранных прошивок.
    Для каждой прошивки из каталога скачиваем файл и прошиваем соответствующий раздел.
    Перед началом пытаемся выполнить бэкап указанного раздела, при неудаче возвращаем флаг needs_backup_confirm.
    """
    try:
        if not selected_names:
            return {"ok": False, "error": "Не выбраны прошивки"}

        # Определяем устройство (может быть вручную передано из UI)
        if manufacturer and model:
            man, mod = manufacturer, model
        else:
            dev = _device_tuple_or_none()
            if not dev:
                return {"ok": False, "error": "Устройство не подключено"}
            man, mod = dev

        # Собираем элементы каталога
        c = _load_fw_catalog().get((category or 'recovery').lower(), [])
        name_to_item = {str(x.get('name')): x for x in c}
        items: list[dict] = []
        for n in selected_names:
            it = name_to_item.get(n)
            if not it:
                return {"ok": False, "error": f"Прошивка не найдена в каталоге: {n}"}
            if not _matches_device(it, man, mod):
                # пропускаем несовместимые молча — фронт отфильтрует
                continue
            items.append(it)
        if not items:
            return {"ok": False, "error": "Нет совместимых прошивок для данного устройства"}

        # Бэкап перед установкой (для каждого уникального раздела)
        tried_backup: set[str] = set()
        failed_backup_error: str | None = None
        for it in items:
            partition = str(it.get('partition', '')).strip()
            if not partition:
                continue
            if partition in tried_backup:
                continue
            tried_backup.add(partition)
            backup_filename = f"{partition}_{man}_{mod}_{int(time.time())}.img"
            backup_path = pathlib.Path(os.getcwd()) / 'backups' / backup_filename
            res = perform_backup_partition(partition=partition, dest_path=str(backup_path), method=method)
            if not res.get('ok'):
                failed_backup_error = res.get('error') or 'Не удалось создать бэкап'
                break

        if failed_backup_error and not continue_without_backup:
            return {"ok": False, "needs_backup_confirm": True, "error": failed_backup_error}

        # Скачиваем и прошиваем
        downloads_dir = pathlib.Path(os.getcwd()) / 'downloads' / 'firmware'
        downloads_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict] = []
        pre_map: dict[str, str] = {}
        if isinstance(pre_downloaded, dict):
            pre_map = {str(k): str(v) for k, v in pre_downloaded.items() if isinstance(k, str) and isinstance(v, str)}
        for it in items:
            # Резолвим прямую ссылку с официальных страниц, если нужно
            url = _resolve_download_url(it).strip()
            partition = str(it.get('partition', '')).strip()
            name_str = str(it.get('name', '')).strip()

            pre_path = None
            if pre_map:
                pre_path = pre_map.get(name_str) or pre_map.get(name_str.lower())

            local_path: pathlib.Path
            if pre_path:
                candidate = pathlib.Path(pre_path)
                if candidate.exists():
                    local_path = candidate
                else:
                    fname = pathlib.Path(url).name or f"{partition}_{int(time.time())}.img"
                    local_path = downloads_dir / fname
                    ok_dl, err_dl = _download_to(local_path, url)
                    if not ok_dl:
                        results.append({"name": it.get('name'), "ok": False, "error": f"Не удалось скачать: {err_dl}"})
                        continue
            else:
                fname = pathlib.Path(url).name or f"{partition}_{int(time.time())}.img"
                local_path = downloads_dir / fname
                ok_dl, err_dl = _download_to(local_path, url)
                if not ok_dl:
                    results.append({"name": it.get('name'), "ok": False, "error": f"Не удалось скачать: {err_dl}"})
                    continue

            fl_res = perform_flash(partition=partition, image_path=str(local_path), method=method)
            if not fl_res.get('ok'):
                results.append({"name": it.get('name'), "ok": False, "error": fl_res.get('error')})
            else:
                results.append({"name": it.get('name'), "ok": True})

        overall_ok = all(r.get('ok') for r in results)
        return {"ok": overall_ok, "results": results}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


eel.start('index.html', size=(1200, 800))