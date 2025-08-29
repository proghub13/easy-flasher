import os
import subprocess


def _fastboot_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'fastboot.exe')


def flash_system(image_path: str) -> None:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f'Не найден образ: {image_path}')
    subprocess.check_call([_fastboot_path(), 'flash', 'system', image_path])

