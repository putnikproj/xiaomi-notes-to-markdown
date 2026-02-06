# Xiaomi Notes to Markdown

Converts Xiaomi/MIUI Notes backup files to Markdown.

## Prerequisites

- Python 3 installed - https://www.python.org/downloads/

## Getting the Backup File

1. On your Xiaomi phone: **Settings → About phone → Back up and restore → Mobile device**
2. Under "Other system app data", select only **Notes**
3. Create the backup
4. Open **File Manager → Internal shared storage → MIUI → backup → AllBackup**
5. Find the folder with `date_time` pattern (e.g., `20240115_120000`)
6. Copy `Notes(com.miui.notes).bak` to the root of this repository

## Usage

```bash
python3 xiaomi_notes_to_md.py
```

Or specify files explicitly:

```bash
python3 xiaomi_notes_to_md.py <backup.bak> [output_dir]
```

Exported notes go to `exported_notes/` by default.

By default, only active notes are exported. The backup file contains all notes ever created, including deleted ones. To include deleted notes:

```bash
python3 xiaomi_notes_to_md.py --include-deleted
```

To also extract images and audio recordings:

```bash
python3 xiaomi_notes_to_md.py --extract-media
```

Media files are saved to `exported_notes/attachments/` and linked in the markdown files.
