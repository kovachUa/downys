import subprocess
import os
import shutil
import sys
import re
import logging
import traceback
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def run_httrack_web_threaded(url, output_dir, kwargs, comm_queue):
    def send(type_, message, details=""):
        data = {"type": type_, "value": message}
        if details:
            data["details"] = details
        comm_queue.put(data)

    def send_status(msg): send("status", msg)
    def send_done(msg): send("done", msg)
    def send_error(msg, details=""): send("error", msg, details)

    try:
        if not url:
            return send_error("Помилка: URL не вказано.", "Будь ласка, надайте дійсний URL.")
        if not output_dir:
            return send_error("Помилка: Не вказано директорію виводу.", "Вкажіть шлях для збереження сайту.")

        if not url.startswith(("http://", "https://")):
            url = "http://" + url

        parent_dir = os.path.abspath(output_dir)
        if not os.path.isdir(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
                send_status(f"Створено директорію виводу: {parent_dir}")
            except Exception as e:
                return send_error(f"Не вдалося створити директорію: {parent_dir}", str(e))

        parsed_url = urlparse(url)
        domain = parsed_url.netloc or ''
        if domain.startswith('www.'):
            domain = domain[4:]
        if not domain:
            return send_error("Неможливо визначити домен з URL.", "Перевірте формат (наприклад, 'http://example.com').")

        site_subdir_name = re.sub(r'[^\w.-]+', '_', domain).strip('_')
        project_dir = os.path.join(parent_dir, site_subdir_name)

        max_depth = kwargs.get('max_depth', 3)
        max_rate = kwargs.get('max_rate', 0)
        sockets = kwargs.get('sockets', 4)
        archive_after = kwargs.get('archive_after_mirror', False)
        archive_path = kwargs.get('post_mirror_archive_path')
        follow_robots = kwargs.get('follow_robots', True)
        mirror_mode = kwargs.get('mirror_mode', 'create')

        # --- ЗМІНЕНО: Команда тепер отримує батьківську директорію (`parent_dir`) ---
        # Це змусить HTTrack створити папку `site_subdir_name` всередині `parent_dir`,
        # уникаючи подвійного вкладення.
        command = [
            'httrack', url,
            '-O', parent_dir, # <--- ОСНОВНА ЗМІНА ТУТ
            '--timeout=20', '--disable-security-limits',
            '--keep-alive',
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--cache=4',
            '--verbose'
        ]
        # --- КІНЕЦЬ ЗМІНИ ---

        if mirror_mode == 'update':
            command.append('--update')
            send_status("Режим: Оновлення існуючого дзеркала.")
            if not os.path.isdir(project_dir):
                send_status(f"Увага: директорія проекту '{project_dir}' не існує. HTTrack може створити її.")
        else:
            command.append('--mirror')
            send_status("Режим: Створення нового дзеркала.")
            if os.path.isdir(project_dir):
                send_status(f"Увага: директорія проекту '{project_dir}' вже існує. HTTrack продовжить завантаження.")

        if follow_robots:
            command.extend(['--robots', '1'])
        else:
            command.extend(['--robots', '0'])
            send_status("Ігнорування robots.txt.")
        
        if max_depth: 
            command.extend(['--depth', str(max_depth)])
        if max_rate > 0: 
            command.extend(['--max-rate', str(max_rate)])
        if sockets > 0: 
            command.extend(['--sockets', str(sockets)])

        send_status(f"Запуск HTTrack для {url}...")
        logger.info(f"HTTrack команда: {' '.join(command)}")

        si = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            bufsize=1, startupinfo=si
        )

        has_output = False
        for line in iter(process.stdout.readline, ''):
            if line:
                line_strip = line.strip()
                send_status(f"HTTrack: {line_strip}")
                has_output = True

        process.wait(timeout=300)
        stdout_rem, stderr_rem = process.communicate()

        if stdout_rem:
            for line in stdout_rem.strip().splitlines():
                send_status(f"HTTrack: {line.strip()}")
                has_output = True

        if process.returncode != 0:
            error_details = stderr_rem.strip()
            if not error_details and has_output:
                error_details = "HTTrack завершився з помилкою. Можливо, були передані невірні аргументи."
            
            logger.error(f"HTTrack завершено з помилкою. Команда: {' '.join(command)}")
            logger.error(f"Код помилки: {process.returncode}")
            logger.error(f"Stderr:\n{stderr_rem}")
            return send_error(
                f"HTTrack завершився з помилкою (код {process.returncode}).",
                f"Деталі:\n{error_details}"
            )

        if not has_output:
            send_status("Завершено без виводу. Можливо, сайт вже повністю завантажено.")

        complete_file = os.path.join(project_dir, 'hts-cache', 'complete.txt')
        if os.path.exists(complete_file):
            send_status("Завантаження успішно завершено!")
        else:
            send_status("Завантаження зупинено. Можна продовжити пізніше.")

        if archive_after and mirror_mode == 'create':
            send_status("Архівація завантаженого сайту...")
            archive_directory_threaded(project_dir, archive_path, {'source_already_validated': True}, comm_queue)
        else:
            # Повідомлення про завершення все ще використовує `project_dir`, що правильно
            send_done(f"Операцію завершено. Сайт знаходиться в {project_dir}.")

    except FileNotFoundError:
        send_error("HTTrack не знайдено.", "Переконайтеся, що HTTrack встановлено і є у PATH.")
    except subprocess.CalledProcessError as e:
        send_error(f"HTTrack завершився з помилкою (код {e.returncode}).",
                   f"Команда: {' '.join(e.cmd)}\nПомилка: {e.stderr}")
    except Exception as e:
        send_error(f"Неочікувана помилка: {e}", traceback.format_exc())


def archive_directory_threaded(directory_to_archive, archive_path, kwargs, comm_queue):
    def send(type_, message, details=""):
        data = {"type": type_, "value": message}
        if details:
            data["details"] = details
        comm_queue.put(data)

    def send_status(msg): send("status", msg)
    def send_done(msg): send("done", msg)
    def send_error(msg, details=""): send("error", msg, details)

    try:
        if not kwargs.get('source_already_validated'):
            if not os.path.isdir(directory_to_archive):
                return send_error(f"Директорія '{directory_to_archive}' не існує.")
            if not archive_path:
                return send_error("Не вказано шлях для архіву.")

        ext = os.path.splitext(archive_path)[1].lower()
        if ext in ['.tar.gz', '.tgz']:
            archive_format = 'gztar'
        elif ext in ['.tar.bz2', '.tbz2']:
            archive_format = 'bztar'
        elif ext == '.zip':
            archive_format = 'zip'
        elif ext == '.tar':
            archive_format = 'tar'
        else:
            return send_error(
                f"Непідтримуваний формат архіву: {archive_path}",
                "Підтримувані формати: .tar.gz, .tgz, .tar.bz2, .tbz2, .zip, .tar"
            )

        archive_dir = os.path.dirname(archive_path)
        if archive_dir and not os.path.exists(archive_dir):
            os.makedirs(archive_dir, exist_ok=True)
            send_status(f"Створено директорію для архіву: {archive_dir}")

        base_name = os.path.splitext(archive_path)[0]
        if base_name.endswith('.tar'):
            base_name = os.path.splitext(base_name)[0]

        send_status(f"Архівування '{os.path.basename(directory_to_archive)}' у '{archive_path}'...")
        final_archive_path = shutil.make_archive(
            base_name, 
            archive_format,
            root_dir=os.path.dirname(os.path.abspath(directory_to_archive)),
            base_dir=os.path.basename(directory_to_archive)
        )

        send_done(f"Архів створено: {os.path.basename(final_archive_path)}")

    except Exception as e:
        send_error(f"Помилка архівації: {e}", traceback.format_exc())
