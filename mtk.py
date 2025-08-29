import os
import subprocess


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def _run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def root(bat_path: str | None = None) -> None:
    # Для MTK чаще используется эксплойт/скрипт. Если есть .bat — запускаем его.
    if bat_path and os.path.exists(bat_path):
        subprocess.check_call(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f'Start-Process -FilePath "{bat_path}"'])
    else:
        raise RuntimeError('Не найден скрипт для рута MTK. Укажите путь к .bat')


def unlock_bootloader() -> None:
    # Для Xiaomi/MTK используем комплект скриптов в unlock-mtk-xiaomi
    script_path = os.path.join(os.getcwd(), 'unlock-mtk-xiaomi', 'UnlockBootloader.bat')
    if not os.path.exists(script_path):
        raise RuntimeError('UnlockBootloader.bat не найден')
    subprocess.check_call(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f'Start-Process -Wait -FilePath "{script_path}"'])


def lock_bootloader() -> None:
    script_path = os.path.join(os.getcwd(), 'unlock-mtk-xiaomi', 'LockBootloader.bat')
    if not os.path.exists(script_path):
        raise RuntimeError('LockBootloader.bat не найден')
    subprocess.check_call(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f'Start-Process -Wait -FilePath "{script_path}"'])


def flash_recovery(image_path: str) -> None:
    # Большинство MTK устройств тоже шьются через fastboot для recovery/boot/system
    fastboot = _fastboot_path()
    _run([fastboot, 'flash', 'recovery', image_path])


def flash_system(image_path: str) -> None:
    fastboot = _fastboot_path()
    _run([fastboot, 'flash', 'system', image_path])


def flash_boot(image_path: str) -> None:
    fastboot = _fastboot_path()
    _run([fastboot, 'flash', 'boot', image_path])


def disable_verity_and_verification(vbmeta_path: str | None = None) -> None:
    fastboot = _fastboot_path()
    args = [fastboot]
    if vbmeta_path:
        args += ['--disable-verity', '--disable-verification', 'flash', 'vbmeta', vbmeta_path]
    else:
        args += ['--disable-verity', '--disable-verification', 'flash', 'vbmeta']
    _run(args)
