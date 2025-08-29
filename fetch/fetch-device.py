import subprocess
import re
import os

def get_device_manufacturer():
    try:
        # Указываем путь к adb.exe в папке platform-tools
        adb_path = os.path.join(os.getcwd(), 'platform-tools', 'adb.exe')
        
        # Проверяем подключение устройства
        devices_output = subprocess.check_output([adb_path, 'devices'], text=True).strip()
        if "device" not in devices_output:
            return "Устройство не подключено или отладка по USB не включена."

        # Выполняем команду adb shell getprop для получения полной информации об устройстве
        getprop_output = subprocess.check_output([adb_path, 'shell', 'getprop'], text=True).strip()
        print("Вывод getprop:", getprop_output)  # Выводим полный вывод без ограничения
        
        # Извлекаем свойства производителя
        manufacturer_match = re.search(r'ro.product.manufacturer=([^\n]+)', getprop_output)
        brand_match = re.search(r'ro.product.brand=([^\n]+)', getprop_output)

        manufacturer = manufacturer_match.group(1) if manufacturer_match else "Unknown"
        brand = brand_match.group(1) if brand_match else "Unknown"

        # Логика определения производителя
        if manufacturer != "Unknown":
            return manufacturer.capitalize()
        elif brand != "Unknown":
            # Если brand равен "MTK" (что указывает на процессор), игнорируем его
            if brand.lower() == "mtk":
                return "Unknown (возможно, данные ограничены)"
            return brand.capitalize()
        else:
            return "Не удалось определить производителя"

    except subprocess.CalledProcessError as e:
        return f"Ошибка при выполнении ADB команды: {e}"
    except FileNotFoundError:
        return "Файл adb.exe не найден в папке platform-tools. Проверьте путь."
    except Exception as e:
        return f"Произошла ошибка: {e}"

if __name__ == "__main__":
    manufacturer_info = get_device_manufacturer()
    print(f"Производитель устройства: {manufacturer_info}")