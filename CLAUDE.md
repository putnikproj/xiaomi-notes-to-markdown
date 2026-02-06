# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Single-file Python CLI tool that extracts notes from Xiaomi/MIUI Notes backup files (`.bak`) and exports them as Markdown files.

## Running the Script

```bash
# Auto-detect .bak file in current directory
python xiaomi_notes_to_md.py

# Specify input file and output directory
python xiaomi_notes_to_md.py <backup_file.bak> [output_directory]

# Include deleted notes from backup history
python xiaomi_notes_to_md.py --include-deleted

# Extract images and audio files
python xiaomi_notes_to_md.py --extract-media
```

Output defaults to `exported_notes/` directory. Media files go to `attachments/` subdirectory.

## Architecture

The script processes MIUI backup files through a pipeline:

1. **Binary Parsing** (`find_notes_section`, `extract_notes`): Locates notes data section using marker bytes (`miui_bak/_tmp_bak`), then extracts notes using two methods:
   - Folder marker pattern (`z` + length + `common`/`secret`) to find note boundaries
   - Protobuf-style field tags (`0x12`) as fallback for notes without folder markers

2. **XML Extraction** (`extract_xml_content`): Notes use custom XML markup with tags like `<text>`, `<bullet>`, `<quote>`, `<input type="checkbox">`, etc.

3. **Markdown Conversion** (`xml_to_markdown`): Converts Xiaomi's XML format to standard Markdown, handling headers (`<size>`, `<mid-size>`), formatting (`<b>`, `<i>`, `<delete>`), lists, blockquotes, and media references.

4. **Media Extraction** (`extract_attachments`): Finds `miui_att/` entries in the backup, detects file types (JPEG, PNG, MP3) by signatures, and extracts binary content.

5. **Export** (`export_notes`, `save_attachments`): Writes individual `.md` files with sanitized filenames, handling duplicates with numeric suffixes. Optionally saves media to `attachments/` and updates markdown links.

## Data Model

`Note` dataclass with `title`, `content`, and `folder` (either "common" or "secret").

## Known Limitations

- Binary format is reverse-engineered; some notes may not parse correctly
- Without `--extract-media`, attachments show as placeholders (`[Audio: fileid]`, `[Image: hash]`)
- Media extraction supports JPEG, PNG, and MP3 formats
