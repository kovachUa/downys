import subprocess
import os
import shutil
import sys 
import time
from urllib.parse import urlparse
import re
import logging

logger = logging.getLogger(__name__)

def run_httrack_web_threaded(url, output_dir, kwargs, comm_queue): 
    max_depth = kwargs.get('max_depth', 3)
    max_rate = kwargs.get('max_rate', 50000)
    sockets = kwargs.get('sockets', 2)
    archive_after = kwargs.get('archive_after_mirror', False)
    archive_path = kwargs.get('post_mirror_archive_path', None)

    def send_status(message):
        comm_queue.put({"type": "status", "value": message})
    def send_done(message):
        comm_queue.put({"type": "done", "value": message})
    def send_error(message):
        comm_queue.put({"type": "error", "value": message})
        
    try:
        if not url or not output_dir:
            raise ValueError("Не вказано URL або директорію для HTTrack.")

        parent_dir = os.path.dirname(output_dir)
        if parent_dir and not os.path.isdir(parent_dir):
            raise FileNotFoundError(f"Батьківська директорія не існує: {parent_dir}")

        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain.startswith('www.'): domain = domain[4:]
        site_subdir_name = re.sub(r'[^\w.-]+', '_', domain).strip('_')

        command = [
            'httrack', url, '-O', output_dir,
            '--robots=0', '--timeout=30', '--disable-security-limits',
            '--keep-alive', '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            f'-* +*.{domain}/*'
        ]
        
        if max_depth is not None: command.extend(['--depth', str(max_depth)])
        if max_rate is not None and max_rate > 0: command.extend(['--max-rate', str(max_rate)])
        if sockets is not None and sockets > 0: command.extend(['--sockets', str(sockets)])

        send_status(f"Запуск HTTrack для {url}...")
        logger.info(f"Executing HTTrack command: {' '.join(command)}")

        si = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE 

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   text=True, encoding='utf-8', errors='replace',
                                   bufsize=1, startupinfo=si)

        for line in iter(process.stdout.readline, ''):
            if line: send_status(f"HTTrack: {line.strip()}")
        
        stdout_rem, stderr_rem = process.communicate()
        if process.returncode != 0:
            error_message = f"HTTrack завершився з помилкою (код {process.returncode}).\n\nStderr:\n{stderr_rem.strip()}\n\nStdout:\n{stdout_rem.strip()}"
            raise subprocess.CalledProcessError(process.returncode, command, output=stdout_rem, stderr=stderr_rem)

        send_status(f"HTTrack успішно завершено.")

        if archive_after:
            final_mirror_dir = os.path.join(output_dir, site_subdir_name)
            if not os.path.isdir(final_mirror_dir):
                 logger.warning(f"Could not find expected mirror directory '{final_mirror_dir}'. Will try to archive parent '{output_dir}'.")
                 final_mirror_dir = output_dir

            archive_directory_threaded(final_mirror_dir, archive_path, {'source_already_validated': True}, comm_queue)
        else:
             send_done(f"Сайт збережено в {output_dir}.")

    except FileNotFoundError:
        send_error("Команда 'httrack' не знайдена. Переконайтеся, що HTTrack встановлено і доступний у PATH.")
    except Exception as e:
        import traceback
        error_msg = f"Неочікувана помилка під час виконання HTTrack: {e}\n{traceback.format_exc()}"
        logger.critical(error_msg)
        send_error(error_msg)

def archive_directory_threaded(directory_to_archive, archive_path, kwargs, comm_queue):
    def send_status(message):
        comm_queue.put({"type": "status", "value": message})
    def send_done(message):
        comm_queue.put({"type": "done", "value": message})
    def send_error(message):
        comm_queue.put({"type": "error", "value": message})
        
    try:
        if not kwargs.get('source_already_validated'):
            if not directory_to_archive or not os.path.isdir(directory_to_archive):
                raise FileNotFoundError(f"Директорія для архівування не знайдена: {directory_to_archive}")
            if not archive_path:
                raise ValueError("Не вказано шлях для файлу архіву.")

        archive_format = None
        path_lower = archive_path.lower()
        if path_lower.endswith(('.tar.gz', '.tgz')): archive_format = 'gztar'
        elif path_lower.endswith(('.tar.bz2', '.tbz2')): archive_format = 'bztar'
        elif path_lower.endswith('.zip'): archive_format = 'zip'
        elif path_lower.endswith('.tar'): archive_format = 'tar'
        else:
            raise ValueError(f"Непідтримуваний формат архіву для: {archive_path}")

        archive_parent_dir = os.path.dirname(archive_path)
        if archive_parent_dir and not os.path.isdir(archive_parent_dir):
            os.makedirs(archive_parent_dir, exist_ok=True)
            send_status(f"Створено директорію для архіву: {archive_parent_dir}")

        root_dir_for_archive = os.path.dirname(os.path.abspath(directory_to_archive))
        base_dir_for_archive = os.path.basename(directory_to_archive)
        
        archive_base_name = os.path.splitext(archive_path)[0]
        if archive_base_name.endswith('.tar'):
            archive_base_name = os.path.splitext(archive_base_name)[0]

        send_status(f"Архівування '{base_dir_for_archive}' у '{archive_path}'...")
        logger.info(f"Archiving: base_name='{archive_base_name}', format='{archive_format}', root_dir='{root_dir_for_archive}', base_dir='{base_dir_for_archive}'")

        final_archive_path = shutil.make_archive(archive_base_name, archive_format, root_dir_for_archive, base_dir_for_archive)
        send_done(f"Архівування завершено: {os.path.basename(final_archive_path)}")

    except Exception as e:
        import traceback
        error_msg = f"Помилка під час архівації: {e}\n{traceback.format_exc()}"
        logger.critical(error_msg)
        send_error(error_msg)
