import os
import re
from tqdm import tqdm

BUFFER_SIZE = 4096

def upload_file_to_server(host, port, file_path, update_progress_callback=None):
    print("Завантаження файлу локально...")

    try:
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # Створення папки, якщо її немає
        folder_path = os.path.dirname(file_path)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # Замінюємо небажані символи в іменах файлів
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

        # Вивести прогрес завантаження
        with open(file_path, "rb") as file:
            sent_size = 0
            while chunk := file.read(BUFFER_SIZE):
                sent_size += len(chunk)
                if update_progress_callback:
                    update_progress_callback(sent_size / file_size)
            print(f"Файл {safe_filename} успішно завантажено локально (розмір: {file_size} байт)")

    except Exception as e:
        print(f"Помилка при завантаженні файлу: {e}")
