import os
import subprocess
import zipfile
import tempfile
import shutil
from django.conf import settings
from django.core import management
from django.utils import timezone


def get_backups_dir():
    """
    إرجاع مسار مجلد النسخ الاحتياطية على السيرفر
    يُقرأ من settings.SERVER_BACKUPS_DIR (يوجد داخل المشروع)
    """
    backups_dir = settings.SERVER_BACKUPS_DIR
    os.makedirs(backups_dir, exist_ok=True)
    return backups_dir


def create_backup(backup_note=""):
    """
    محرك النسخ الاحتياطي الشامل
    يحاول استخدام mysqldump أولاً، وإذا فشل يستخدم Django dumpdata
    ثم يضيف ملفات الميديا ويكوم الكل في ملف ZIP
    """
    temp_dir = tempfile.mkdtemp()
    db_backup_sql = os.path.join(temp_dir, 'db_backup.sql')
    db_backup_json = os.path.join(temp_dir, 'db_backup.json')
    media_backup_file = os.path.join(temp_dir, 'media_backup.zip')
    
    current_time = timezone.now().strftime("%Y-%m-%d_at_%H-%M")
    
    # تنظيف الملاحظة من الرموز الخطيرة
    safe_note = "".join(c for c in backup_note if c.isalnum() or c in (' ', '_', '-', '(', ')')).strip()
    safe_note = safe_note.replace(' ', '_')
    
    if safe_note:
        final_backup_file = os.path.join(temp_dir, f'Accounting_Backup_{current_time}_{safe_note}.zip')
    else:
        final_backup_file = os.path.join(temp_dir, f'Accounting_Backup_{current_time}.zip')

    backup_method = 'unknown'

    # ==========================================
    # 1. نسخ قاعدة البيانات
    # ==========================================
    try:
        db_settings = settings.DATABASES['default']
        db_user = db_settings.get('USER', 'root')
        db_password = db_settings.get('PASSWORD', '')
        db_host = db_settings.get('HOST', 'localhost')
        db_port = db_settings.get('PORT', '3306')
        db_name = db_settings.get('NAME')

        command = [
            'mysqldump',
            f'-u{db_user}',
            f'-h{db_host}',
            f'--port={db_port}',
            '--default-character-set=utf8mb4',
            '--single-transaction',
            '--skip-lock-tables',
            '--add-drop-table',
        ]
        
        if db_password:
            command.append(f'-p{db_password}')
            
        command.append(db_name)
        
        with open(db_backup_sql, 'wb') as f:
            process = subprocess.Popen(
                command, 
                stdout=f, 
                stderr=subprocess.PIPE, 
                stdin=subprocess.DEVNULL
            )
            _, error = process.communicate(timeout=60)
            
            if process.returncode != 0:
                error_msg = error.decode('utf-8', errors='replace')
                raise Exception(f"mysqldump error code {process.returncode}: {error_msg}")
        
        backup_method = 'mysql_dump'
        
    except Exception as e:
        print(f"--- mysqldump failed: {str(e)} ---")
        print(f"--- Falling back to Django dumpdata... ---")
        try:
            with open(db_backup_json, 'w', encoding='utf-8') as f:
                management.call_command(
                    'dumpdata', 
                    exclude=['contenttypes', 'auth.permissions'], 
                    output=f.name, 
                    indent=2
                )
            backup_method = 'django_json'
        except Exception as json_e:
            raise Exception(f"Both backup methods failed. Django error: {str(json_e)}")

    # ==========================================
    # 2. ضغط مجلد الميديا (الصور والملفات)
    # ==========================================
    if hasattr(settings, 'MEDIA_ROOT') and os.path.exists(settings.MEDIA_ROOT):
        with zipfile.ZipFile(media_backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(settings.MEDIA_ROOT):
                if 'safety_backups' in dirs:
                    dirs.remove('safety_backups')
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, settings.MEDIA_ROOT)
                    zipf.write(file_path, arcname)

    # ==========================================
    # 3. دمج الكل في ملف ZIP نهائي
    # ==========================================
    with zipfile.ZipFile(final_backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if backup_method == 'mysql_dump' and os.path.exists(db_backup_sql):
            zipf.write(db_backup_sql, 'database_backup.sql')
        elif backup_method == 'django_json' and os.path.exists(db_backup_json):
            zipf.write(db_backup_json, 'database_backup.json')
            
        if os.path.exists(media_backup_file):
            zipf.write(media_backup_file, 'media_backup.zip')
            
        info_file = os.path.join(temp_dir, 'backup_info.txt')
        with open(info_file, 'w', encoding='utf-8') as f:
            f.write(f"Backup Method: {backup_method}\n")
            f.write(f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if safe_note:
                f.write(f"Note: {backup_note}\n")
        zipf.write(info_file, 'backup_info.txt')

    return final_backup_file


def save_backup_to_server(temp_file_path, prefix=""):
    """
    تنسخ ملف النسخة من المجلد المؤقت إلى مجلد النسخ الدائم على السيرفر
    prefix: لبادئة مثل 'Restore_a_backup_' لتمييز نسخ الاسترجاع
    """
    backups_dir = get_backups_dir()
    filename = prefix + os.path.basename(temp_file_path)
    permanent_path = os.path.join(backups_dir, filename)
    
    shutil.copy2(temp_file_path, permanent_path)
    
    return permanent_path, filename


def get_server_backups():
    """
    ترجع قائمة بجميع النسخ الاحتياطية المخزنة على السيرفر
    مرتبة من الأحدث إلى الأقدم
    """
    backups_dir = get_backups_dir()
    backups = []
    
    if not os.path.exists(backups_dir):
        return backups
    
    for filename in os.listdir(backups_dir):
        if not filename.endswith('.zip'):
            continue
            
        filepath = os.path.join(backups_dir, filename)
        if not os.path.isfile(filepath):
            continue
        
        # تجاهل أي ملفات قديمة لا تتبع النمط الصحيح
        if not (filename.startswith('Accounting_Backup_') or filename.startswith('Restore_a_backup_')):
            continue
        
        stat = os.stat(filepath)
        size_bytes = stat.st_size
        
        # تحويل الحجم لصيغة مقروءة
        if size_bytes < 1024:
            size_human = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_human = f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            size_human = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_human = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
        
        # استخراج التاريخ والوقت والملاحظة ونوع النسخة
        created = "غير معروف"
        note = ""
        is_safety = False
        
        try:
            clean_name = filename.replace('.zip', '')
            
            # التعرف على نسخ الاسترجاع بالبادئة الجديدة
            if clean_name.startswith('Restore_a_backup_'):
                is_safety = True
                clean_name = clean_name.replace('Restore_a_backup_', '')
            else:
                clean_name = clean_name.replace('Accounting_Backup_', '')
            
            parts = clean_name.split('_')
            
            if len(parts) >= 3:
                date_part = parts[0]
                time_part = parts[2]
                created = f"{date_part} الساعة {time_part.replace('-', ':')}"
            
            if len(parts) > 3:
                note = ' '.join(parts[3:])
        except:
            pass
        
        backups.append({
            'filename': filename,
            'filepath': filepath,
            'size': size_bytes,
            'size_human': size_human,
            'created': created,
            'note': note,
            'is_safety': is_safety,
        })
    
    # ترتيب تنازلي (الأحدث أولاً)
    backups.sort(key=lambda x: x['filename'], reverse=True)
    
    return backups


def delete_server_backup(filename):
    """
    حذف نسخة احتياطية من السيرفر مع التحقق من الأمان
    """
    backups_dir = get_backups_dir()
    filepath = os.path.join(backups_dir, filename)
    
    # التحقق من أن الملف ينتمي لهذا المجلد (حماية من Path Traversal)
    if not os.path.abspath(filepath).startswith(os.path.abspath(backups_dir)):
        raise PermissionError("مسار غير آمن")
    
    if not os.path.exists(filepath):
        raise FileNotFoundError("الملف غير موجود")
        
    os.remove(filepath)
    return True