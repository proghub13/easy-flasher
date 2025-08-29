import os
import subprocess


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def _run(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def unlock_bootloader() -> None:
    adb = _adb_path()
    fastboot = _fastboot_path()
    # Перезагружаем в fastboot и разблокируем загрузчик (подтверждение на экране устройства)
    _run([adb, 'reboot', 'bootloader'])
    _run([fastboot, 'oem', 'unlock'])


def lock_bootloader() -> None:
    fastboot = _fastboot_path()
    _run([fastboot, 'oem', 'lock'])


def flash_recovery(image_path: str) -> None:
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
    # Если передан путь к пустому vbmeta — используем его, иначе ключи применятся к существующему
    if vbmeta_path:
        args += ['--disable-verity', '--disable-verification', 'flash', 'vbmeta', vbmeta_path]
    else:
        args += ['--disable-verity', '--disable-verification', 'flash', 'vbmeta']
    _run(args)


