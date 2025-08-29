import os
import subprocess
from typing import Optional


def _embedded_python_path(base_dir: str) -> str:
    return os.path.join(base_dir, 'file', 'python.exe')


def _assert_mtkclient(base_dir: str) -> None:
    if not os.path.exists(_embedded_python_path(base_dir)):
        raise FileNotFoundError('Не найден встроенный python.exe (file/python.exe)')
    if not os.path.isdir(os.path.join(base_dir, 'mtkclient')):
        raise FileNotFoundError('Не найден модуль mtkclient (mtkclient/)')


def testpoint_flash_partition(partition: str, image_path: str,
                              base_dir: Optional[str] = None,
                              preloader_path: Optional[str] = None,
                              auth_path: Optional[str] = None,
                              extra_args: Optional[list[str]] = None) -> None:
    """
    Шьёт раздел через режим testpoint. Для MTK используется тот же mtkclient,
    но требуется физический вход в testpoint согласно инструкции модели.
    """
    if not base_dir:
        base_dir = os.path.join(os.getcwd(), 'unlock-mtk-xiaomi')
    _assert_mtkclient(base_dir)
    if not os.path.exists(image_path):
        raise FileNotFoundError(f'Не найден образ: {image_path}')

    cmd: list[str] = [_embedded_python_path(base_dir), '-m', 'mtkclient', 'w', partition, image_path]
    if preloader_path:
        cmd += ['--preloader', preloader_path]
    if auth_path:
        cmd += ['--auth', auth_path]
    if extra_args:
        cmd += extra_args

    subprocess.check_call(cmd, cwd=base_dir)


def testpoint_read_partition(partition: str, out_path: str,
                             base_dir: Optional[str] = None,
                             preloader_path: Optional[str] = None,
                             auth_path: Optional[str] = None,
                             extra_args: Optional[list[str]] = None) -> None:
    if not base_dir:
        base_dir = os.path.join(os.getcwd(), 'unlock-mtk-xiaomi')
    _assert_mtkclient(base_dir)
    if not os.path.isdir(os.path.dirname(os.path.abspath(out_path))):
        raise FileNotFoundError('Каталог для сохранения дампа не найден')

    cmd: list[str] = [_embedded_python_path(base_dir), '-m', 'mtkclient', 'r', partition, out_path]
    if preloader_path:
        cmd += ['--preloader', preloader_path]
    if auth_path:
        cmd += ['--auth', auth_path]
    if extra_args:
        cmd += extra_args

    subprocess.check_call(cmd, cwd=base_dir)


