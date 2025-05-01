# --- START OF FILE scripts/distro_tasks.py ---

import requests
import hashlib
import os
import sys
import subprocess
import shutil
import time
from urllib.parse import urlparse
import GLib # For idle_add if needed directly (usually not needed here)

CHUNK_SIZE = 8192

def calculate_hash(filename, algorithm='sha256', status_callback=None):
    """Обчислює хеш-суму файлу заданим алгоритмом."""
    hasher = None
    if algorithm == 'sha256':
        hasher = hashlib.sha256()
    elif algorithm == 'sha512':
        hasher = hashlib.sha512()
    else:
        raise ValueError(f"Непідтримуваний алгоритм хешування: {algorithm}")

    if status_callback:
        GLib.idle_add(status_callback, f"Обчислення {algorithm.upper()} хешу для {os.path.basename(filename)}...")

    try:
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        calculated = hasher.hexdigest()
        if status_callback:
             GLib.idle_add(status_callback, f"Обчислений {algorithm.upper()} хеш: {calculated[:10]}...") # Show partial hash
        return calculated
    except FileNotFoundError:
        raise FileNotFoundError(f"Не вдалося відкрити файл '{filename}' для обчислення хешу.")
    except Exception as e:
        raise RuntimeError(f"Не вдалося обчислити хеш файлу '{filename}': {e}")

def download_file_with_progress(url, destination_path, status_callback=None, progress_callback=None):
    """Завантажує файл з URL з відображенням прогресу."""
    filename = os.path.basename(destination_path)
    if status_callback:
        GLib.idle_add(status_callback, f"Завантаження '{filename}' з {url}...")
    if progress_callback:
        GLib.idle_add(progress_callback, 0.0)

    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded_size = 0

            if status_callback:
                size_mb = f"{total_size / (1024*1024):.2f} MB" if total_size else "Розмір невідомий"
                GLib.idle_add(status_callback, f"Завантаження '{filename}' ({size_mb})...")

            with open(destination_path, 'wb') as f:
                start_time = time.time()
                last_update_time = start_time
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        current_time = time.time()
                        # Оновлювати прогрес не частіше ніж раз на 0.2 секунди
                        if progress_callback and total_size > 0 and (current_time - last_update_time > 0.2 or downloaded_size == total_size):
                             fraction = min(1.0, downloaded_size / total_size)
                             GLib.idle_add(progress_callback, fraction)
                             last_update_time = current_time
                        elif progress_callback and total_size == 0 and (current_time - last_update_time > 0.5):
                             # Якщо розмір невідомий, просто оновлюємо статус
                             if status_callback:
                                 GLib.idle_add(status_callback, f"Завантажено {downloaded_size / (1024*1024):.2f} MB...")
                             last_update_time = current_time


        if progress_callback:
             GLib.idle_add(progress_callback, 1.0) # Ensure 100% at the end
        if status_callback:
            GLib.idle_add(status_callback, f"Завантаження '{filename}' завершено.")
        return destination_path # Повертаємо шлях до завантаженого файлу

    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Помилка мережі під час завантаження: {e}")
    except Exception as e:
        # Clean up partially downloaded file on generic error
        if os.path.exists(destination_path):
            try:
                os.remove(destination_path)
            except OSError as rm_err:
                print(f"Warning: Could not remove partially downloaded file '{destination_path}': {rm_err}", file=sys.stderr)
        raise RuntimeError(f"Неочікувана помилка під час завантаження: {e}")


def run_dd_command(source_file, target_disk, status_callback=None):
    """Виконує команду dd для запису файлу на диск."""
    if not os.path.exists(source_file):
        raise FileNotFoundError(f"Вхідний файл не знайдено: {source_file}")
    if not target_disk or not target_disk.startswith('/dev/'):
         raise ValueError("Неприпустимий цільовий диск. Шлях має починатися з /dev/.")
    # НЕ перевіряємо os.path.exists(target_disk), бо це блоковий пристрій

    filename = os.path.basename(source_file)
    if status_callback:
        GLib.idle_add(status_callback, f"Запис '{filename}' на диск '{target_disk}' за допомогою dd...")
        GLib.idle_add(status_callback, "Це може зайняти тривалий час. Потрібні права адміністратора (sudo)...")

    # Важливо: status=progress може не працювати на старих версіях dd
    # conv=fsync дуже важливий для гарантії запису
    dd_command = [
        'sudo', 'dd',
        f'if={source_file}',
        f'of={target_disk}',
        'bs=4M',
        'status=progress',
        'conv=fsync'
    ]

    try:
        # Використовуємо Popen для потенційного читання stderr (для прогресу, якщо status=progress не працює)
        # Але простіше покластися на status=progress і check=True
        process = subprocess.run(dd_command, check=True, capture_output=True, text=True)
        # Прогрес виводиться dd в stderr, якщо status=progress працює
        if status_callback:
             # Спробуємо вивести stderr, де може бути інформація про прогрес або завершення
             # print("DD stderr:\n", process.stderr) # Для дебагу
             lines = process.stderr.strip().split('\n')
             last_line = lines[-1] if lines else "Інформація від dd відсутня."
             GLib.idle_add(status_callback, f"dd завершено. Остання інформація: {last_line}")
             GLib.idle_add(status_callback, f"Запис '{filename}' на '{target_disk}' успішно завершено.")

    except FileNotFoundError:
         raise FileNotFoundError("Команда 'sudo' або 'dd' не знайдена. Переконайтесь, що вони встановлені та доступні в PATH.")
    except subprocess.CalledProcessError as e:
        # dd може повернути помилку через недостатньо прав, неправильний диск, тощо.
        error_message = f"Помилка dd (код {e.returncode}): {e.stderr.strip()}"
        if "Permission denied" in e.stderr and "sudo" in dd_command[0]:
             error_message += "\nМожлива причина: Не вдалося отримати права sudo (напр., невірний пароль або недостатньо прав)."
        elif "No such file or directory" in e.stderr and f"of={target_disk}" in " ".join(e.cmd):
             error_message += f"\nМожлива причина: Цільовий пристрій '{target_disk}' не існує або недоступний."
        elif "No space left on device" in e.stderr:
             error_message += f"\nМожлива причина: Недостатньо місця на цільовому пристрої '{target_disk}'."

        raise RuntimeError(error_message)
    except Exception as e:
         raise RuntimeError(f"Неочікувана помилка під час виконання dd: {e}")

# --- END OF FILE scripts/distro_tasks.py ---
# --- END OF FILE scripts/distro_tasks.py ---
