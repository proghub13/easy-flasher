import subprocess
import re
import os

def get_cpu_info():
    try:
        # Указываем путь к adb.exe в папке platform-tools
        adb_path = os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')
        
        # Проверяем подключение устройства
        devices_output = subprocess.check_output([adb_path, 'devices'], text=True).strip()
        if "device" not in devices_output:
            return "Устройство не подключено или отладка по USB не включена."

        # Выполняем команду adb shell cat /proc/cpuinfo
        cpuinfo_output = subprocess.check_output([adb_path, 'shell', 'cat', '/proc/cpuinfo'], text=True).strip()
        print("Вывод /proc/cpuinfo:", cpuinfo_output or "Пусто")
        
        # Выполняем команду adb shell getprop для дополнительной информации
        getprop_output = subprocess.check_output([adb_path, 'shell', 'getprop'], text=True).strip()
        print("Вывод getprop (ro.board.platform):", re.search(r'ro.board.platform=([^\n]+)', getprop_output).group(0) if re.search(r'ro.board.platform=([^\n]+)', getprop_output) else "Не найдено")
        
        # Ищем модель процессора в cpuinfo
        cpu_model = "Не удалось определить"
        for line in cpuinfo_output.splitlines():
            if "Processor" in line or "model name" in line:
                cpu_model = line.split(":")[1].strip()
                break
            elif "Hardware" in line:
                hardware = line.split(":")[1].strip().lower()
                if "mt" in hardware:
                    return "MediaTek"
                elif "msm" in hardware or "qcom" in hardware:
                    return "Не поддерживается (Qualcomm/Snapdragon)"
        
        # Если в cpuinfo нет данных, проверяем платформу через getprop
        if "Не удалось определить" in cpu_model or not cpu_model:
            platform_match = re.search(r'ro.board.platform=([^\n]+)', getprop_output)
            if platform_match:
                platform = platform_match.group(1).lower()
                if "mt" in platform:
                    return "MediaTek"
                elif "msm" in platform or "qcom" in platform:
                    return "Не поддерживается (Qualcomm/Snapdragon)"
            else:
                # Попытка извлечь информацию из ro.product.board
                board_match = re.search(r'ro.product.board=([^\n]+)', getprop_output)
                if board_match:
                    board = board_match.group(1).lower()
                    if "mt" in board:
                        return "MediaTek"
                    elif "msm" in board or "qcom" in board:
                        return "Не поддерживается (Qualcomm/Snapdragon)"
        
        # Дополнительная проверка по cpu_model
        if cpu_model.lower().find("mediatek") != -1:
            return "MediaTek"
        elif cpu_model.lower().find("snapdragon") != -1 or cpu_model.lower().find("qualcomm") != -1:
            return "Не поддерживается (Qualcomm/Snapdragon)"
        
        return "Не удалось определить"

    except subprocess.CalledProcessError as e:
        return f"Ошибка при выполнении ADB команды: {e}"
    except FileNotFoundError:
        return "Файл adb.exe не найден в папке platform-tools. Проверьте путь."
    except Exception as e:
        return f"Произошла ошибка: {e}"