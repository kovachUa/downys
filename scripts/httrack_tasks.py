# scripts/httrack_tasks.py
import subprocess
import os
import shutil
import sys # Додано для можливого використання sys.platform
from gi.repository import GLib
import time
from urllib.parse import urlparse
import re


def run_httrack_web_threaded(url, output_dir, status_callback, **kwargs): # Додано **kwargs для гнучкості
    if not url or not output_dir:
        if status_callback: GLib.idle_add(status_callback, "Помилка: Не вказано URL або директорію для HTTrack.")
        raise ValueError("Не вказано URL або директорію для HTTrack.")

    # Перевірка батьківської директорії (залишено як у вашому оригіналі, main.py вже має логіку створення output_dir)
    parent_dir = os.path.dirname(output_dir)
    if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Батьківська директорія не існує: {parent_dir}")
        raise FileNotFoundError(f"Батьківська директорія не існує: {parent_dir}")

    command = ['httrack', url, '-O', output_dir, '--clean']
    if status_callback: GLib.idle_add(status_callback, f"Запуск HTTrack для {url} у {output_dir}...")

    try:
        # Для Windows можна налаштувати startupinfo, щоб приховати консольне вікно httrack
        si = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE # Приховує вікно

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   text=True, bufsize=1, startupinfo=si)

        while True:
            if process.poll() is not None: # Перевірка, чи процес завершився
                break

            # Намагаємося читати з stdout (більш імовірно для прогресу)
            line_read_stdout = process.stdout.readline()
            if line_read_stdout:
                line_read_stdout = line_read_stdout.strip()
                if line_read_stdout and status_callback: # Якщо рядок не порожній після strip
                    GLib.idle_add(status_callback, f"HTTrack: {line_read_stdout[:150]}...")
                # Якщо рядок прочитано, продовжуємо наступну ітерацію, щоб пріоритезувати подальший stdout та перевірити poll
                continue

            # Якщо stdout нічого не повернув (або EOF), намагаємося читати з stderr
            line_read_stderr = process.stderr.readline()
            if line_read_stderr:
                line_read_stderr = line_read_stderr.strip()
                if line_read_stderr and status_callback: # Якщо рядок не порожній після strip
                    GLib.idle_add(status_callback, f"HTTrack (err): {line_read_stderr[:150]}...")
                # Якщо рядок прочитано, продовжуємо наступну ітерацію
                continue

            # Якщо обидва readline() повернули порожній рядок (EOF для цього потоку)
            # і процес все ще виконується, коротко засинаємо.
            if process.poll() is None: # Перевіряємо poll ще раз перед сном
                time.sleep(0.05) # Невелика пауза, якщо немає виводу, а процес живий

        # Процес завершився, чекаємо на нього та отримуємо залишковий вивід
        return_code = process.wait() # Гарантує, що процес завершено та ресурси звільнено

        stdout_remainder = process.stdout.read() # Читаємо будь-які залишкові дані
        stderr_remainder = process.stderr.read()

        # Обробка будь-якого залишкового виводу (в основному для налагодження)
        if stdout_remainder.strip() and status_callback:
            for rem_line in stdout_remainder.strip().splitlines():
                 if rem_line.strip(): GLib.idle_add(status_callback, f"HTTrack (rem_out): {rem_line.strip()[:150]}...")
        if stderr_remainder.strip() and status_callback:
            for rem_line in stderr_remainder.strip().splitlines():
                 if rem_line.strip(): GLib.idle_add(status_callback, f"HTTrack (rem_err): {rem_line.strip()[:150]}...")


        if return_code != 0:
            error_message_parts = [f"HTTrack завершився з помилкою (код {return_code})."]
            # Використовуємо повністю прочитані stderr_remainder та stdout_remainder
            if stderr_remainder.strip(): # Пріоритет stderr для повідомлень про помилки
                 error_message_parts.append(f"Повідомлення з stderr (останні 1000 символів):\n{stderr_remainder.strip()[-1000:]}")
            elif stdout_remainder.strip():
                 error_message_parts.append(f"Повідомлення з stdout (останні 1000 символів):\n{stdout_remainder.strip()[-1000:]}")
            
            full_error_message = "\n".join(error_message_parts)
            # Конструктор CalledProcessError приймає stdout та stderr як аргументи
            raise subprocess.CalledProcessError(return_code, command, output=stdout_remainder, stderr=stderr_remainder)

        if status_callback: GLib.idle_add(status_callback, f"HTTrack успішно завершено. Сайт збережено в {output_dir}.")

    except FileNotFoundError: # Якщо команда 'httrack' не знайдена
        if status_callback: GLib.idle_add(status_callback, "Помилка: Команда 'httrack' не знайдена.")
        raise RuntimeError("Помилка: Команда 'httrack' не знайдена. Переконайтеся, що HTTrack встановлено і доступний у PATH.")
    except subprocess.CalledProcessError as e:
        # Створюємо більш інформативне повідомлення з помилки
        error_output_msg = "Немає додаткового виводу."
        # e.stderr та e.stdout будуть заповнені, оскільки ми їх передали при створенні винятку
        if e.stderr and e.stderr.strip():
            error_output_msg = f"Stderr: {e.stderr.strip()[-1000:]}"
        elif e.stdout and e.stdout.strip(): 
            error_output_msg = f"Stdout: {e.stdout.strip()[-1000:]}"
        if status_callback: GLib.idle_add(status_callback, f"Помилка виконання HTTrack: {e.returncode}")
        raise RuntimeError(f"Помилка виконання HTTrack (код {e.returncode}):\n{error_output_msg}")
    except Exception as e: # Інші неочікувані помилки
        if status_callback: GLib.idle_add(status_callback, f"Неочікувана помилка HTTrack: {e}")
        raise RuntimeError(f"Неочікувана помилка при запуску HTTrack: {e}")


def archive_directory_threaded(directory_to_archive, archive_path, status_callback, site_subdir_name=None, site_url=None):
    """
    Архівує ДИРЕКТОРІЮ САЙТУ (піддиректорію) або вказану директорію в zip або tar.gz файл.
    """
    if not directory_to_archive or not os.path.isdir(directory_to_archive):
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Базова директорія для архівування не знайдена або не є директорією: {directory_to_archive}")
        raise FileNotFoundError(f"Базова директорія для архівування не знайдена або не є директорією: {directory_to_archive}")
    if not archive_path:
        if status_callback: GLib.idle_add(status_callback, "Помилка: Не вказано шлях для файлу архіву.")
        raise ValueError("Не вказано шлях для файлу архіву.")

    archive_format = None
    if archive_path.lower().endswith('.zip'):
        archive_format = 'zip'
    elif archive_path.lower().endswith('.tar.gz') or archive_path.lower().endswith('.tgz'):
        archive_format = 'gztar'
    elif archive_path.lower().endswith('.tar.bz2') or archive_path.lower().endswith('.tbz'):
         archive_format = 'bztar'
    elif archive_path.lower().endswith('.tar'):
         archive_format = 'tar'
    else:
        ext = os.path.splitext(archive_path)[1]
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Непідтримуваний формат архіву: {ext}")
        raise ValueError(f"Непідтримуваний формат архіву: {ext}")

    directory_to_include_in_archive = directory_to_archive
    # target_directory_in_base_dir = None # Змінна не використовується, можна видалити

    # Логіка визначення піддиректорії сайту для архівування
    # Якщо HTTrack зберігає сайт у піддиректорію всередині output_dir
    if site_subdir_name or site_url:
         actual_subdir_name = site_subdir_name
         if not actual_subdir_name and site_url: # Якщо є URL, спробувати отримати ім'я піддиректорії з нього
              try:
                 parsed_url = urlparse(site_url)
                 hostname = parsed_url.hostname
                 if hostname:
                      # HTTrack часто використовує ім'я хоста як назву проекту/піддиректорії
                      # Видаляємо 'www.' та санітизуємо
                      if hostname.startswith("www."):
                           hostname = hostname[4:]
                      # Проста санітизація, HTTrack може мати складнішу логіку
                      actual_subdir_name = re.sub(r'[^\w.-]', '_', hostname).strip('_') 
                      # HTTrack також може включати шлях у назву, це складніше передбачити
                      # Наприклад, example.com/path -> example.com/path
                      # Наразі обмежуємося хостом.
              except Exception:
                 pass # Не вдалося отримати ім'я з URL

         if actual_subdir_name:
              # Повний шлях до очікуваної піддиректорії сайту
              full_site_subdir_path = os.path.join(directory_to_archive, actual_subdir_name)

              if os.path.isdir(full_site_subdir_path):
                   directory_to_include_in_archive = full_site_subdir_path
                   # target_directory_in_base_dir = actual_subdir_name # Не використовується
                   if status_callback: GLib.idle_add(status_callback, f"Знайдено піддиректорію сайту: {actual_subdir_name}. Архівуємо її.")
              else:
                   # Якщо піддиректорія не знайдена, архівуємо всю базову директорію, як і раніше
                   if status_callback: GLib.idle_add(status_callback, f"Попередження: Піддиректорія сайту '{actual_subdir_name}' не знайдена в '{directory_to_archive}'. Архівуємо всю директорію '{os.path.basename(directory_to_archive)}'.")
         else:
              if status_callback: GLib.idle_add(status_callback, f"Попередження: Не вдалося визначити назву піддиректорії сайту з URL '{site_url}'. Архівуємо всю директорію '{os.path.basename(directory_to_archive)}'.")

    # root_dir: директорія, відносно якої будуть шляхи в архіві.
    # base_dir: шлях до директорії, яку архівуємо, відносно root_dir.
    # Щоб уникнути повних шляхів в архіві, встановлюємо root_dir на батьківську директорію того, що архівуємо.
    root_dir_for_archive = os.path.dirname(os.path.abspath(directory_to_include_in_archive))
    base_dir_for_archive = os.path.basename(directory_to_include_in_archive)

    # Спеціальний випадок: якщо архівуємо поточну директорію (наприклад, ".")
    if os.path.abspath(directory_to_include_in_archive) == os.path.abspath(os.getcwd()):
        root_dir_for_archive = os.getcwd() # Або батьківська директорія, якщо base_dir "."
        base_dir_for_archive = "." # Архівувати вміст поточної директорії
        if status_callback: GLib.idle_add(status_callback, "Налаштування для архівування вмісту поточної директорії.")


    # Видаляємо розширення з імені файлу архіву для shutil.make_archive
    archive_base_name_for_shutil = os.path.join(os.path.dirname(archive_path), 
                                                os.path.splitext(os.path.basename(archive_path))[0])
    # Для .tar.gz/.tar.bz2 потрібно видалити два розширення
    if archive_format in ['gztar', 'bztar'] and archive_base_name_for_shutil.lower().endswith('.tar'):
         archive_base_name_for_shutil = os.path.splitext(archive_base_name_for_shutil)[0]


    archive_parent_dir = os.path.dirname(archive_path) # Директорія, де буде збережено архів
    if not archive_parent_dir: # Якщо шлях відносний і без директорії
        archive_parent_dir = "." # Поточна директорія

    if not os.path.isdir(archive_parent_dir): # Переконуємося, що директорія для архіву існує
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Батьківська директорія для архіву не існує: {archive_parent_dir}")
        raise FileNotFoundError(f"Батьківська директорія для архіву не існує: {archive_parent_dir}")


    if status_callback:
        GLib.idle_add(status_callback, f"Архівування '{base_dir_for_archive}' (з '{root_dir_for_archive}') у '{archive_path}'...")

    try:
        # shutil.make_archive(base_name, format, root_dir=None, base_dir=None, ...)
        # base_name - це шлях до архіву БЕЗ розширення формату
        # root_dir - директорія, відносно якої base_dir
        # base_dir - що саме архівувати (відносно root_dir)
        final_archive_path = shutil.make_archive(archive_base_name_for_shutil,
                                                 archive_format,
                                                 root_dir=root_dir_for_archive,
                                                 base_dir=base_dir_for_archive)


        if status_callback: GLib.idle_add(status_callback, f"Архівування завершено: {os.path.basename(final_archive_path)}")

    except FileNotFoundError: # Може виникнути, якщо немає утиліт zip/tar
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Не знайдено утиліти для формату '{archive_format}'.")
        raise RuntimeError(f"Помилка: Не знайдено утиліти для створення архіву формату '{archive_format}'. Переконайтеся, що встановлено zip/tar/gzip/bzip2.")
    except Exception as e:
        if status_callback: GLib.idle_add(status_callback, f"Помилка під час архівації директорії: {e}")
        raise RuntimeError(f"Помилка під час архівації директорії: {e}")
