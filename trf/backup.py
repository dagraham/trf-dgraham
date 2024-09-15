import os
import zipfile
import re
from datetime import datetime, timedelta
# from . import logger

# Backup and restore functions

def backup_to_zip(trf_home, today, logger):
    backup_dir = os.path.join(trf_home, 'backup')
    files_to_backup = [os.path.join(trf_home, 'trf.fs'), os.path.join(trf_home, 'trf.fs.index')]
    logger.debug(f"{files_to_backup = }")
    if not files_to_backup or not os.path.exists(files_to_backup[0]):
        return False, "nothing to backup"

    last_modified_timestamp = os.path.getmtime(files_to_backup[0])
    last_modified_time = datetime.fromtimestamp(last_modified_timestamp)

    for file in files_to_backup:
        if not os.path.exists(file):
            return (False, f"Backup skipped - {file} does not exist")

    if today == 'remove':
        files_to_backup += [os.path.join(trf_home, 'trf.fs.tmp'), os.path.join(trf_home, 'trf.fs.lock')]
        backup_zip = os.path.join(trf_home, 'backup', "removed.zip")
    else:
        backup_zip = os.path.join(trf_home, 'backup', f"{last_modified_time.strftime('%y%m%d')}.zip")
        if os.path.exists(backup_zip):
            return (False, f"Backup skipped - backup file already exists: {backup_zip}")

    with zipfile.ZipFile(backup_zip, 'w') as zipf:
        for file in files_to_backup:
            zipf.write(file)

    if today == 'remove':
        for fp in files_to_backup:
            if os.path.exists(fp):
                os.remove(fp)
        return (True, "Backup completed and original files removed.")

    return (True, f"Backup completed: {backup_zip}")

def rotate_backups(trf_home, logger):
    # entry point for backups - make sure backup dir exists
    backup_dir = os.path.join(trf_home, 'backup')
    os.makedirs(backup_dir, exist_ok=True)

    today = datetime.today()
    ok, msg = backup_to_zip(trf_home, today, logger)
    if not ok:
        logger.info(msg)
        return False

    pattern = re.compile(r'^\d{6}\.zip$')
    all_files = os.listdir(backup_dir)
    names = [os.path.splitext(f)[0] for f in all_files if pattern.match(f)]
    queue = []
    gap = timedelta(days=14)

    names.sort()
    remove = []
    for name in names:
        queue.insert(0, name)
        if len(queue) > 7:
            pivot = queue[3]
            older = queue[4]
            pivot_dt = datetime.strptime(pivot, "%y%m%d")
            pivot_gap = (pivot_dt - gap).strftime("%y%m%d")
            if older < pivot_gap:
                remove.append(queue.pop(-1))
            else:
                remove.append(queue.pop(3))

            if len(queue) > 7:
                remove.extend(queue[7:])
                queue = queue[:7]

    if remove:
        for name in remove:
            file = os.path.join(backup_dir, f"{name}.zip")
            os.remove(file)
        logger.info(f"Removing backup: {', '.join(remove)}")

def restore_from_zip(trf_home):
    clear_screen()
    backup_dir = os.path.join(trf_home, 'backup')
    print(f"""
Choosing one of the 'restore from' options will:
1) compress all trf.fs* files into "remove.zip" in {backup_dir}
2) remove all trf.fs* files from {trf_home}
3) restore files "trf.fs" and "trf.fs.index" from the selected zip file
""")

    pattern = re.compile(r'^\d{6}\.zip$')
    all_files = os.listdir(backup_dir)
    names = [os.path.splitext(f)[0] for f in all_files if pattern.match(f)]
    names.sort(reverse=True)

    restore_options = {'0': 'cancel'}
    for i, name in enumerate(names, 1):
        restore_options[str(i)] = name

    while True:
        print("Options:")
        for opt, value in restore_options.items():
            print(f"    {opt}: restore from '{value}'" if opt != '0' else f"    {opt}: {restore_options[opt]}")

        choice = input("Choose an option: ").strip().lower()
        if choice in restore_options:
            if choice == '0':
                print("Restore cancelled.")
                return False, "nothing to backup"

            # Perform the restore
            ok, msg = backup_to_zip(track_home, 'remove')
            print(msg)
            chosen_name = restore_options[choice]
            backup_zip = os.path.join(backup_dir, chosen_name + '.zip')
            print(f"Extracting files from {backup_zip}")

            with zipfile.ZipFile(backup_zip, 'r') as zipf:
                zipf.extractall(track_home)

            return

        else:
            print("Invalid option. Please choose again.")
