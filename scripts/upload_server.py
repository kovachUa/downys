import os
import socket
from tqdm import tqdm

BUFFER_SIZE = 4096

def upload_file_to_server(host, port, file_path, update_progress_callback=None):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(b"upload")
            response = s.recv(BUFFER_SIZE)
            if response != b"UPLOAD_READY":
                print("Сервер не готовий прийняти файл.")
                return

            filename = os.path.basename(file_path)
            s.sendall(filename.encode())
            response = s.recv(BUFFER_SIZE)
            if response != b"FILENAME_RECEIVED":
                print("Сервер не підтвердив отримання імені файлу.")
                return

            file_size = os.path.getsize(file_path)
            s.sendall(str(file_size).encode())
            response = s.recv(BUFFER_SIZE)
            if response != b"SIZE_RECEIVED":
                print("Сервер не підтвердив отримання розміру файлу.")
                return

            with open(file_path, "rb") as file:
                sent_size = 0
                while chunk := file.read(BUFFER_SIZE):
                    s.sendall(chunk)
                    sent_size += len(chunk)
                    if update_progress_callback:
                        update_progress_callback(sent_size / file_size)
            print("Файл успішно завантажено на сервер")
    except Exception as e:
        print(f"Помилка при завантаженні файлу: {e}")
 
