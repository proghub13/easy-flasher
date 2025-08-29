import eel
import traceback
import mtk
import brom as brom_flash
import testpoint as tp_flash
import snapdragon
from flash.root import root as root_helper
from flash.system import flash_sys as flash_sys_helper
from flash.recMode import flash_recovery as flash_recovery_helper
from recovery import recovery as recovery_helper
from fetch import fetch_proc
import os
import subprocess
import json


eel.init("web")


def _detect_soc() -> str:
    cpu = fetch_proc.get_cpu_info()
    if cpu not in ("MediaTek", "Snapdragon"):
        raise RuntimeError(f"Не удалось определить SoC: {cpu}")
    return cpu


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def _adb(*args: str) -> str:
    return subprocess.check_output([_adb_path(), *args], text=True).strip()


def _fastboot(*args: str) -> str:
    return subprocess.check_output([_fastboot_path(), *args], text=True, stderr=subprocess.STDOUT).strip()


def _ensure_device_online() -> None:
    out = _adb('devices')
    if '\tdevice' not in out:
        raise RuntimeError('Устройство не подключено или отладка по USB не включена')


# Ручные переопределения производителя/модели (если ADB не дал данные)
MANUAL_MANUFACTURER: str | None = None
MANUAL_MODEL: str | None = None


def _reboot_to_bootloader() -> None:
    try:
        _fastboot('devices')
        return
    except Exception:
        pass
    _adb('reboot', 'bootloader')


def _is_bootloader_unlocked() -> bool:
    out = _fastboot('getvar', 'unlocked')
    # Примеры: "unlocked: yes" или вывод из device-info
    if 'unlocked: yes' in out.lower():
        return True
    try:
        out2 = _fastboot('oem', 'device-info')
        for line in out2.lower().splitlines():
            if 'device unlocked' in line and ('true' in line or 'yes' in line):
                return True
    except Exception:
        pass
    return False


def _get_manufacturer_and_model() -> tuple[str, str]:
    try:
        props = _adb('shell', 'getprop')
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
        return manufacturer, model
    except Exception:
        return (MANUAL_MANUFACTURER or 'Unknown', MANUAL_MODEL or 'Unknown')


def _load_special_profiles() -> dict:
    try:
        with open(os.path.join(os.getcwd(), 'special_devices.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"no_unlock_required": [], "no_fastboot_reboot": [], "instructions": []}


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


@eel.expose
def perform_root(image_path: str | None = None, method: str = 'auto'):
    try:
        soc = _detect_soc()
        manufacturer, model = _get_manufacturer_and_model()
        if manufacturer == 'Unknown' or model == 'Unknown':
            return {
                "ok": False,
                "manual_ident": True,
                "manufacturers": [
                    "xiaomi", "google", "oneplus", "samsung", "huawei", "lg", "sony", "meizu", "oppo", "realme", "vivo", "motorola", "nokia"
                ],
                "message": "Не удалось определить производителя/модель через ADB. Укажите вручную (можно посмотреть в Настройки > О телефоне или в AIDA64)."
            }
        _ensure_device_online()
        no_unlock = _is_in_profiles(manufacturer, model, 'no_unlock_required')
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')
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
                _reboot_to_bootloader()
            else:
                return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model)}
            if not _is_bootloader_unlocked():
                return {
                    "ok": False,
                    "needs_unlock": True,
                    "manufacturer": manufacturer,
                    "model": model,
                    "message": "Загрузчик заблокирован. Нужна разблокировка через Brom."
                }
            # Разблокирован — продолжаем рут: требуется патченный boot
            if not image_path:
                raise RuntimeError("Укажите путь к патченному boot.img для рута")
            # Отключаем verity/verification и прошиваем patched boot
            vbmeta_path = os.path.join('unlock-mtk-xiaomi', 'vbmeta.img.empty')
            try:
                mtk.disable_verity_and_verification(vbmeta_path if os.path.exists(vbmeta_path) else None)
            except Exception:
                pass
            mtk.flash_boot(image_path)
            return {"ok": True, "message": "root завершён"}
        else:
            # Общая схема (Snapdragon и прочие): нужен патченный boot
            if not image_path:
                raise RuntimeError("Укажите путь к патченному boot.img для рута")
            if not no_cmd_fastboot:
                _reboot_to_bootloader()
            else:
                return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model)}
            try:
                snapdragon.disable_verity_and_verification()
            except Exception:
                pass
            snapdragon.flash_boot(image_path)
            return {"ok": True, "message": "root завершён"}
    except Exception:
        err = traceback.format_exc()
        print(err)
        return {"ok": False, "error": err}


@eel.expose
def perform_unlock(method: str = 'auto'):
    try:
        soc = _detect_soc()
        manufacturer, model = _get_manufacturer_and_model()
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')
        if method == 'brom' and soc == 'MediaTek':
            return {"ok": False, "needs_unlock": True, "message": "Brom: выключите устройство, удерживайте Vol− и подключите USB. Затем подтвердите на устройстве."}
        if method == 'testpoint':
            return {"ok": False, "manual_fastboot": True, "instructions": _get_device_instructions(manufacturer, model) or [
                "Откройте устройство (на ваш риск)",
                "Замкните testpoint контакты согласно руководству вашей модели",
                "Подключите USB, войдите в загрузчик",
                "Вернитесь в приложение и продолжите"
            ]}
        if soc == "MediaTek":
            if not no_cmd_fastboot:
                _reboot_to_bootloader()
            mtk.unlock_bootloader()
        else:
            _reboot_to_bootloader()
            snapdragon.unlock_bootloader()
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
        soc = _detect_soc()
        manufacturer, model = _get_manufacturer_and_model()
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
        manufacturer, model = _get_manufacturer_and_model()
        no_cmd_fastboot = _is_in_profiles(manufacturer, model, 'no_fastboot_reboot')
        if method == 'brom' and soc == 'MediaTek':
            # Выполняем прошивку через BROM. Пользователь должен ввести устройство в BROM (Vol− на выключенном).
            brom_flash.brom_flash_partition(partition, image_path)
            return {"ok": True}
        if method == 'testpoint':
            # Прошивка через testpoint. Требуется аппаратный вход в TP.
            tp_flash.testpoint_flash_partition(partition, image_path)
            return {"ok": True}
        # Для fastboot не важно SoC, но оставим на будущее
        if partition == 'recovery':
            flash_recovery_helper.flash_recovery(image_path)
        elif partition == 'system':
            flash_sys_helper.flash_system(image_path)
        elif partition == 'boot':
            if soc == 'MediaTek':
                mtk.flash_boot(image_path)
            else:
                snapdragon.flash_boot(image_path)
        else:
            raise RuntimeError(f"Неизвестный раздел: {partition}")
        return {"ok": True}
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


eel.start('index.html', size=(1200, 800))