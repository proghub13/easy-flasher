import os
import subprocess
import time
import mtk


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def push_magisk_boot(image_path: str) -> None:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f'Не найден образ: {image_path}')
    subprocess.check_call([_adb_path(), 'push', image_path, '/sdcard/magisk_patched.img'])


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def _adb(*args: str) -> str:
    return subprocess.check_output([_adb_path(), *args], text=True).strip()


def _fastboot(*args: str) -> str:
    return subprocess.check_output([_fastboot_path(), *args], text=True, stderr=subprocess.STDOUT).strip()


def _has_fastboot_device() -> bool:
    try:
        out = _fastboot('devices')
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if '\tfastboot' in line or line.endswith('fastboot') or ('\t' in line and line.split('\t')[-1]):
                return True
        return False
    except Exception:
        return False


def _has_adb_device() -> bool:
    try:
        out = _adb('devices')
        return '\tdevice' in out
    except Exception:
        return False


def _ensure_fastboot_auto(wait_seconds: int = 30) -> dict | None:
    if _has_fastboot_device():
        return None
    if _has_adb_device():
        try:
            _adb('reboot', 'fastboot')
        except Exception:
            pass
        time.sleep(max(1, wait_seconds))
        if _has_fastboot_device():
            return None
        if _has_adb_device():
            return {"ok": False, "error": "Вручную перейдите в fastboot и повторите операцию"}
        return {"ok": False, "error": "Подключите устройство"}
    return {"ok": False, "error": "Подключите устройство"}


def perform_mtk_root(image_path: str) -> dict:
    if not image_path:
        return {"ok": False, "error": "Укажите путь к патченному boot.img для рута"}
    ensure = _ensure_fastboot_auto()
    if ensure is not None:
        return ensure
    try:
        vbmeta_path = os.path.join('unlock-mtk-xiaomi', 'vbmeta.img.empty')
        mtk.disable_verity_and_verification(vbmeta_path if os.path.exists(vbmeta_path) else None)
    except Exception:
        pass
    mtk.flash_boot(image_path)
    return {"ok": True, "message": "root завершён"}

