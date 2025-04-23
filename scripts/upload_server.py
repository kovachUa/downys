import os
import socket
from gi.repository import GLib # Import GLib

BUFFER_SIZE = 4096

def upload_file_to_server(host, port, file_path, update_progress_callback=None):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = os.path.getsize(file_path)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))

            s.sendall(b"upload")
            response = s.recv(BUFFER_SIZE)
            if response != b"UPLOAD_READY":
                raise RuntimeError(f"Сервер не готовий до завантаження. Відповідь: {response.decode(errors='ignore')}")

            filename = os.path.basename(file_path)
            s.sendall(filename.encode())
            response = s.recv(BUFFER_SIZE)
            if response != b"FILENAME_RECEIVED":
                raise RuntimeError(f"Сервер не підтвердив отримання імені файлу. Відповідь: {response.decode(errors='ignore')}")

            s.sendall(str(file_size).encode())
            response = s.recv(BUFFER_SIZE)
            if response != b"SIZE_RECEIVED":
                 raise RuntimeError(f"Сервер не підтвердив отримання розміру файлу. Відповідь: {response.decode(errors='ignore')}")

            sent_size = 0
            with open(file_path, "rb") as file:
                while True:
                    chunk = file.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    s.sendall(chunk)
                    sent_size += len(chunk)

                    if update_progress_callback:
                        fraction = sent_size / file_size
                        # Use GLib.idle_add to safely update UI from thread
                        GLib.idle_add(update_progress_callback, fraction)

            # Send confirmation or wait for server confirmation if needed
            # For simplicity, assuming sending all data is success confirmation

            return True

    except ConnectionRefusedError:
        raise RuntimeError(f"Помилка: Не вдалося підключитись до сервера за адресою {host}:{port}. Переконайтеся, що сервер запущений.")
    except FileNotFoundError:
        # This is checked at the beginning, but keeping it for completeness
        raise FileNotFoundError(f"Файл для завантаження не знайдено: {file_path}")
    except Exception as e:
        raise RuntimeError(f"Помилка під час завантаження на сервер: {e}")
