import os
import subprocess


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def push_magisk_boot(image_path: str) -> None:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f'Не найден образ: {image_path}')
    subprocess.check_call([_adb_path(), 'push', image_path, '/sdcard/magisk_patched.img'])

