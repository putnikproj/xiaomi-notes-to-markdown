#!/usr/bin/env python3
"""
Xiaomi Notes Backup to Markdown Converter

Parses MIUI Notes backup files (.bak) and exports notes as Markdown files.
"""

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Note:
    """Represents a parsed Xiaomi Note."""
    title: str
    content: str
    folder: str = "common"


def find_notes_section(data: bytes) -> bytes:
    """Find and extract the notes data section from the backup."""
    marker = b'miui_bak/_tmp_bak'
    start_idx = data.find(marker)
    if start_idx == -1:
        return data

    data = data[start_idx:]

    # Find end of notes data
    end_markers = [b'miui_att/', b'apps/com.miui.notes/miui_att']
    for end_marker in end_markers:
        end_idx = data.find(end_marker)
        if end_idx != -1 and end_idx > 1000:
            data = data[:end_idx]
            break

    return data


def extract_notes(data: bytes, include_deleted: bool = False) -> list[Note]:
    """Extract notes from the binary data.

    Args:
        data: Binary backup data
        include_deleted: If True, include deleted notes from backup history
    """
    notes = []
    seen_titles = set()

    # Find all folder markers (end of each note record)
    # Pattern: z + length_byte + folder_name (common or secret)
    # Active notes have \x28\x00\x30\x00 (field 6 = 0) before the folder marker
    folder_pattern = re.compile(rb'z.(common|secret)')
    folder_matches = list(folder_pattern.finditer(data))

    # Extract notes from segments between folder markers
    for i, match in enumerate(folder_matches):
        folder_name = match.group(1).decode('utf-8')

        # Get the segment for this note
        if i > 0:
            segment_start = folder_matches[i - 1].end()
        else:
            segment_start = 0

        segment_end = match.end()
        segment = data[segment_start:segment_end]

        # Find the title using r + length + title + z pattern
        title_match = re.search(
            rb'r(.)([\x20-\xff]{1,200}?)z.(?:common|secret)$',
            segment,
            re.DOTALL
        )

        if title_match:
            title_len = title_match.group(1)[0]
            title_bytes = title_match.group(2)
            if title_len <= len(title_bytes):
                title = title_bytes[:title_len].decode('utf-8', errors='replace')
            else:
                title = title_bytes.decode('utf-8', errors='replace')
        else:
            continue

        title = clean_title(title)
        if not title or title in seen_titles:
            continue

        seen_titles.add(title)

        # Extract XML content from this segment
        xml_content = extract_xml_content(segment.decode('utf-8', errors='replace'))

        notes.append(Note(
            title=title,
            content=xml_content if xml_content else title,
            folder=folder_name
        ))

    # Extract deleted notes from protobuf-style records (only if requested)
    if include_deleted:
        pos = 0
        while pos < len(data) - 3:
            if data[pos] == 0x12:  # Field 2 tag
                length = data[pos + 1]

                if 2 <= length <= 200 and pos + 2 + length <= len(data):
                    title_bytes = data[pos + 2:pos + 2 + length]

                    try:
                        title = title_bytes.decode('utf-8')

                        # Filter for valid titles
                        if (any(c.isalpha() for c in title) and
                            not title.startswith('<') and
                            not title.startswith('vnd.') and
                            not title.endswith('.mp3') and
                            not title.endswith('.jpeg') and
                            title not in ('false', 'true') and
                            len(title) >= 2):

                            clean = clean_title(title)
                            if clean and clean not in seen_titles:
                                seen_titles.add(clean)
                                notes.append(Note(
                                    title=clean,
                                    content=clean,  # No content for these
                                    folder="common"
                                ))

                            pos += 2 + length
                            continue
                    except UnicodeDecodeError:
                        pass

            pos += 1

    return notes


def extract_xml_content(text: str) -> str:
    """Extract XML-formatted content from a note segment."""
    # Find XML content block - it appears twice, take the first complete block
    # The content ends at J followed by a high byte (separator before MIME type)

    first_tag = re.search(r'<(new-format|text|bullet|order|input|hr|quote|sound)', text)
    if not first_tag:
        return ""

    xml_section = text[first_tag.start():]

    # Find where the XML content ends
    # Pattern: closing tag followed by J and high byte (0x80-0xff) = field separator
    # The pattern is: </quote>J\xNN or </text>J\xNN where \xNN is a high byte
    separator_match = re.search(r'(</quote>|</text>|/>)J[\x80-\xff]', xml_section)
    if separator_match:
        # Include the closing tag, exclude J and separator
        xml_section = xml_section[:separator_match.end() - 2]
    else:
        # Fallback - look for MIME type marker
        mime_match = re.search(r'vnd\.android', xml_section)
        if mime_match and mime_match.start() > 10:
            xml_section = xml_section[:mime_match.start()]
            # Find last valid closing tag
            last_close = max(
                xml_section.rfind('</quote>'),
                xml_section.rfind('</text>'),
                xml_section.rfind('<hr />'),
                xml_section.rfind('/>'),
            )
            if last_close > 0:
                close_pos = xml_section.find('>', last_close)
                if close_pos > 0:
                    xml_section = xml_section[:close_pos + 1]

    return xml_section


def clean_title(title: str) -> str:
    """Clean up a note title."""
    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
    title = title.replace('�', '')
    title = title.strip()
    title = re.sub(r'^[^\w\dА-Яа-яЁё]+', '', title)
    title = re.sub(r'[^\w\dА-Яа-яЁё!?.\)]+$', '', title)
    if len(title) > 100:
        title = title[:100]
    return title if title else ""


def xml_to_markdown(xml_content: str) -> str:
    """Convert Xiaomi Notes XML markup to Markdown."""
    if not xml_content:
        return ""

    content = xml_content

    # Remove <new-format/> marker
    content = re.sub(r'<new-format\s*/?\s*>', '', content)

    # Process sound attachments
    content = re.sub(
        r'<sound\s+fileid="([^"]+)"\s*/?>',
        r'[Audio: \1]',
        content
    )

    # Process image references
    content = re.sub(
        r'[\x01☺]\s*([a-f0-9]{40})',
        r'[Image: \1]',
        content
    )

    # Process checkboxes
    content = re.sub(
        r'<input\s+type="checkbox"[^/]*/>\s*([^\n<]+)',
        r'- [ ] \1\n',
        content
    )

    # Process bullets
    content = re.sub(
        r'<bullet\s+indent="\d+"[^/]*/>\s*([^\n<]+)',
        lambda m: f'- {m.group(1).strip()}\n',
        content
    )

    # Process ordered lists
    content = re.sub(
        r'<order\s+indent="\d+"[^/]*/>\s*([^\n<]+)',
        lambda m: f'1. {m.group(1).strip()}\n',
        content
    )

    # Process horizontal rules
    content = re.sub(r'<hr\s*/?\s*>', '\n---\n', content)

    # Process quotes
    def process_quote(m):
        quote_content = m.group(1)
        # Extract text from nested text tags
        lines = re.findall(r'<text[^>]*>([^<]*(?:<[^>]+>[^<]*</[^>]+>)?[^<]*)</text>', quote_content)
        if lines:
            # Clean formatting from each line
            cleaned_lines = []
            for line in lines:
                line = re.sub(r'<center>([^<]+)</center>', r'\1', line)
                line = re.sub(r'<right>([^<]+)</right>', r'\1', line)
                line = re.sub(r'<[^>]+>', '', line)
                cleaned_lines.append('> ' + line.strip())
            return '\n' + '\n'.join(cleaned_lines) + '\n'
        return '> ' + re.sub(r'<[^>]+>', '', quote_content).strip()

    content = re.sub(
        r'<quote>(.+?)</quote>',
        process_quote,
        content,
        flags=re.DOTALL
    )

    # Process text tags with formatting
    def process_text_tag(m):
        inner = m.group(1)

        # Headers
        inner = re.sub(r'<size>([^<]+)</size>', r'# \1', inner)
        inner = re.sub(r'<mid-size>([^<]+)</mid-size>', r'## \1', inner)
        inner = re.sub(r'<h3-size>([^<]+)</h3-size>', r'### \1', inner)

        # Text formatting
        inner = re.sub(r'<b>([^<]+)</b>', r'**\1**', inner)
        inner = re.sub(r'<i>([^<]+)</i>', r'*\1*', inner)
        inner = re.sub(r'<u>([^<]+)</u>', r'_\1_', inner)
        inner = re.sub(r'<delete>([^<]+)</delete>', r'~~\1~~', inner)
        inner = re.sub(r'<background[^>]*>([^<]+)</background>', r'==\1==', inner)

        # Alignment
        inner = re.sub(r'<center>([^<]+)</center>', r'\1', inner)
        inner = re.sub(r'<right>([^<]+)</right>', r'\1', inner)

        return inner + '\n'

    content = re.sub(
        r'<text[^>]*>([^<]*(?:<[^/][^>]*>[^<]*</[^>]+>)*[^<]*)</text>',
        process_text_tag,
        content
    )

    # Clean up remaining XML tags
    content = re.sub(r'<[^>]+/?>', '', content)

    # Clean up stray angle brackets (but preserve > at start of lines for blockquotes)
    content = re.sub(r'<(?![a-zA-Z/])', '', content)
    # Only remove > that's not part of a blockquote (blockquote > is after newline or at start)
    content = re.sub(r'(?<![\n\ra-zA-Z"\'])>', '', content)

    # Clean up special characters
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
    content = content.replace('�', '')

    # Clean up multiple newlines
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Unescape HTML entities
    content = html.unescape(content)

    return content.strip()


def sanitize_filename(title: str) -> str:
    """Create a valid filename from a note title."""
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    filename = re.sub(r'\s+', ' ', filename).strip()

    if len(filename) > 80:
        filename = filename[:80]

    return filename if filename else "untitled"


def export_notes(notes: list[Note], output_dir: str) -> int:
    """Export notes to Markdown files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported = 0
    seen_titles = {}

    for note in notes:
        md_content = xml_to_markdown(note.content)

        if not md_content or len(md_content.strip()) < 2:
            if note.title and len(note.title) > 2:
                md_content = ""
            else:
                continue

        base_filename = sanitize_filename(note.title)
        if not base_filename:
            base_filename = f"note_{exported + 1}"

        if base_filename in seen_titles:
            seen_titles[base_filename] += 1
            filename = f"{base_filename}_{seen_titles[base_filename]}.md"
        else:
            seen_titles[base_filename] = 0
            filename = f"{base_filename}.md"

        filepath = output_path / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {note.title}\n\n")
            if md_content:
                f.write(md_content)
                f.write('\n')

        print(f"  {filename}")
        exported += 1

    return exported


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert Xiaomi/MIUI Notes backup files to Markdown'
    )
    parser.add_argument(
        'backup_file',
        nargs='?',
        help='Path to .bak backup file (auto-detects if not specified)'
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        default='exported_notes',
        help='Output directory (default: exported_notes)'
    )
    parser.add_argument(
        '--include-deleted',
        action='store_true',
        help='Include deleted notes from backup history'
    )
    args = parser.parse_args()

    if args.backup_file:
        bak_path = args.backup_file
    else:
        bak_files = list(Path('.').glob('*.bak'))
        if not bak_files:
            print("No .bak file found in current directory")
            parser.print_help()
            sys.exit(1)
        bak_path = str(bak_files[0])

    print(f"Reading: {bak_path}")

    with open(bak_path, 'rb') as f:
        data = f.read()

    print(f"File size: {len(data):,} bytes")

    notes_data = find_notes_section(data)
    print(f"Notes section: {len(notes_data):,} bytes")

    notes = extract_notes(notes_data, include_deleted=args.include_deleted)
    print(f"Found {len(notes)} notes" + (" (including deleted)" if args.include_deleted else ""))

    if not notes:
        print("No notes could be extracted.")
        sys.exit(1)

    print(f"\nExporting to: {args.output_dir}/")
    exported = export_notes(notes, args.output_dir)

    print(f"\nExported {exported} notes successfully!")


if __name__ == '__main__':
    main()
