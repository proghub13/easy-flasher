import os
import subprocess


def _adb_path() -> str:
    return os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')


def reboot_to_recovery() -> None:
    subprocess.check_call([_adb_path(), 'reboot', 'recovery'])

