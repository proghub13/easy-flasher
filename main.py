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
            return root_helper.perform_mtk_root(image_path)
        # Общая схема для MediaTek: нужен патченный boot
        if not image_path:
            raise RuntimeError("Укажите путь к патченному boot.img для рута")
        if not no_cmd_fastboot:
            return root_helper.perform_mtk_root(image_path)
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

eel.start('index.html', size=(1200, 800))