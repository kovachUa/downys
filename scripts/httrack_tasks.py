# scripts/httrack_tasks.py
import subprocess
import os
import shutil
import sys
from gi.repository import GLib
import time
from urllib.parse import urlparse
import re


def run_httrack_web_threaded(url, output_dir, status_callback):
    if not url or not output_dir:
        if status_callback: GLib.idle_add(status_callback, "Помилка: Не вказано URL або директорію для HTTrack.")
        raise ValueError("Не вказано URL або директорію для HTTrack.")

    parent_dir = os.path.dirname(output_dir)
    if parent_dir and parent_dir != '.' and not os.path.isdir(parent_dir):
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Батьківська директорія не існує: {parent_dir}")
        raise FileNotFoundError(f"Батьківська директорія не існує: {parent_dir}")


    command = ['httrack', url, '-O', output_dir, '--clean']
    if status_callback: GLib.idle_add(status_callback, f"Запуск HTTrack для {url}...")

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, startupinfo=None)

        while True:
            line = None
            line = process.stderr.readline()
            if not line:
                 line = process.stdout.readline()

            if not line:
                 if process.poll() is not None:
                     break
                 time.sleep(0.01)
                 continue

            line = line.strip()
            if line:
                 if status_callback: GLib.idle_add(status_callback, f"HTTrack: {line[:150]}...")

        stdout_remainder = process.stdout.read()
        stderr_remainder = process.stderr.read()

        return_code = process.wait()

        if return_code != 0:
            error_message = f"HTTrack завершився з помилкою (код {return_code}).\n"
            if stderr_remainder:
                 error_message += f"Stderr (остання частина):\n{stderr_remainder[-1000:]}"
            elif stdout_remainder:
                 error_message += f"Stdout (остання частина):\n{stdout_remainder[-1000:]}"
            raise subprocess.CalledProcessError(return_code, command, stdout=stdout_remainder, stderr=stderr_remainder)

        if status_callback: GLib.idle_add(status_callback, f"HTTrack завершено. Сайт збережено в {output_dir}.")

    except FileNotFoundError:
        raise RuntimeError("Помилка: Команда 'httrack' не знайдена. Переконайтеся, що HTTrack встановлено і доступний у PATH.")
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout
        raise RuntimeError(f"Помилка виконання HTTrack: {e.returncode}\n{error_output[-1000:]}")
    except Exception as e:
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
    target_directory_in_base_dir = None

    if site_subdir_name or site_url:
         subdir_name = site_subdir_name
         if not subdir_name and site_url:
              try:
                 parsed_url = urlparse(site_url)
                 hostname = parsed_url.hostname
                 if hostname:
                      if hostname.startswith("www."):
                           hostname = hostname[4:]
                      subdir_name = re.sub(r'[^\w.-]', '_', hostname)
              except Exception as e:
                 pass

         if subdir_name:
              full_site_subdir_path = os.path.join(directory_to_archive, subdir_name)

              if os.path.isdir(full_site_subdir_path):
                   directory_to_include_in_archive = full_site_subdir_path
                   target_directory_in_base_dir = subdir_name
              else:
                   if status_callback: GLib.idle_add(status_callback, f"Попередження: Піддиректорія сайту '{full_site_subdir_path}' не знайдена. Архівуємо всю базову директорію.")

         else:
              if status_callback: GLib.idle_add(status_callback, f"Попередження: Не вдалося визначити назву піддиректорії сайту з URL {site_url}. Архівуємо всю базову директорію.")


    root_dir_for_archive = os.path.dirname(directory_to_include_in_archive)
    base_dir_for_archive = os.path.basename(directory_to_include_in_archive)

    abs_dir_to_include_in_archive = os.path.abspath(directory_to_include_in_archive)
    if abs_dir_to_include_in_archive == os.path.abspath('.') and not target_directory_in_base_dir:
         root_dir_for_archive = '.'
         base_dir_for_archive = '.'
    elif abs_dir_to_include_in_archive == os.path.abspath('/'):
         if status_callback: GLib.idle_add(status_callback, f"Помилка: Архівування кореневої директорії '{directory_to_include_in_archive}' не підтримується.")
         raise ValueError(f"Архівування кореневої директорії '{directory_to_include_in_archive}' не підтримується.")
    elif not os.path.isabs(directory_to_include_in_archive) and not target_directory_in_base_dir:
         root_dir_for_archive = '.'
         base_dir_for_archive = directory_to_include_in_archive

    else:
        pass


    archive_base_name = os.path.splitext(os.path.basename(archive_path))[0]
    if archive_format in ['gztar', 'bztar']:
         archive_base_name = os.path.splitext(archive_base_name)[0]

    archive_parent_dir = os.path.dirname(archive_path)
    if not archive_parent_dir:
        archive_parent_dir = "."

    if not os.path.isdir(archive_parent_dir):
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Батьківська директорія для архіву не існує: {archive_parent_dir}")
        raise FileNotFoundError(f"Батьківська директорія для архіву не існує: {archive_parent_dir}")


    if status_callback:
        if target_directory_in_base_dir:
             GLib.idle_add(status_callback, f"Архівування папки сайту '{base_dir_for_archive}'...")
        elif directory_to_include_in_archive == '.':
             GLib.idle_add(status_callback, f"Архівування вмісту поточної директорії ('.')...")
        else:
             GLib.idle_add(status_callback, f"Архівування директорії '{base_dir_for_archive}'...")

    try:
        final_archive_path = shutil.make_archive(os.path.join(archive_parent_dir, archive_base_name),
                                                 archive_format,
                                                 root_dir=root_dir_for_archive,
                                                 base_dir=base_dir_for_archive)


        if status_callback: GLib.idle_add(status_callback, f"Архівування завершено: {os.path.basename(final_archive_path)}")

    except FileNotFoundError:
        if status_callback: GLib.idle_add(status_callback, f"Помилка: Не знайдено утиліти для формату '{archive_format}'.")
        raise RuntimeError(f"Помилка: Не знайдено утиліти для створення архіву формату '{archive_format}'. Переконайтеся, що встановлено zip/tar/gzip/bzip2.")
    except Exception as e:
        if status_callback: GLib.idle_add(status_callback, f"Помилка під час архівації директорії: {e}")
        raise RuntimeError(f"Помилка під час архівації директорії: {e}")
