import os
import subprocess
from typing import Optional


def _unlock_dir() -> str:
    return os.path.join(os.getcwd(), 'unlock-mtk-xiaomi')


def _embedded_python_path() -> str:
    # В комплекте unlock-mtk-xiaomi есть встроенный Python
    return os.path.join(_unlock_dir(), 'file', 'python.exe')


def _assert_paths(image_path: str) -> None:
    if not os.path.exists(_embedded_python_path()):
        raise FileNotFoundError('Не найден встроенный python.exe в unlock-mtk-xiaomi/file')
    if not os.path.isdir(os.path.join(_unlock_dir(), 'mtkclient')):
        raise FileNotFoundError('Не найден модуль mtkclient в unlock-mtk-xiaomi/mtkclient')
    if not os.path.exists(image_path):
        raise FileNotFoundError(f'Не найден образ: {image_path}')


def brom_flash_partition(partition: str, image_path: str,
                         preloader_path: Optional[str] = None,
                         auth_path: Optional[str] = None,
                         extra_args: Optional[list[str]] = None) -> None:
    """
    Шьёт раздел через MTK BROM, используя встроенный mtkclient.
    Требуется вручной вход в BROM (зажать Vol− на выключенном устройстве и подключить USB).

    partition: boot|recovery|system|… (раздел, поддерживаемый mtkclient)
    image_path: путь к образу
    preloader_path: путь к preloader.bin (если требуется для вашей модели)
    auth_path: путь к auth файлу (если требуется)
    extra_args: дополнительные аргументы CLI mtkclient
    """
    _assert_paths(image_path)
    python_path = _embedded_python_path()
    cwd = _unlock_dir()

    cmd: list[str] = [python_path, '-m', 'mtkclient', 'w', partition, image_path]
    if preloader_path:
        cmd += ['--preloader', preloader_path]
    if auth_path:
        cmd += ['--auth', auth_path]
    if extra_args:
        cmd += extra_args

    # mtkclient должен запускаться из каталога, где доступен пакет mtkclient
    subprocess.check_call(cmd, cwd=cwd)


def brom_read_partition(partition: str, out_path: str,
                        preloader_path: Optional[str] = None,
                        auth_path: Optional[str] = None,
                        extra_args: Optional[list[str]] = None) -> None:
    """Читает раздел через BROM (дамп)"""
    if not os.path.isdir(os.path.dirname(os.path.abspath(out_path))):
        raise FileNotFoundError('Каталог для сохранения дампа не найден')
    if not os.path.exists(_embedded_python_path()):
        raise FileNotFoundError('Не найден встроенный python.exe в unlock-mtk-xiaomi/file')
    if not os.path.isdir(os.path.join(_unlock_dir(), 'mtkclient')):
        raise FileNotFoundError('Не найден модуль mtkclient в unlock-mtk-xiaomi/mtkclient')

    python_path = _embedded_python_path()
    cwd = _unlock_dir()

    cmd: list[str] = [python_path, '-m', 'mtkclient', 'r', partition, out_path]
    if preloader_path:
        cmd += ['--preloader', preloader_path]
    if auth_path:
        cmd += ['--auth', auth_path]
    if extra_args:
        cmd += extra_args

    subprocess.check_call(cmd, cwd=cwd)


