"""
_scanner/splitter.py — Stage 3: split a flat file into upload-sized chunks.
"""

from datetime import datetime
from pathlib import Path

from _scanner.warnings import FILE_FOOTER

FILE_MARKER = "=" * 60


def _split(text: str, limit: int) -> list[str]:
    """Split at FILE_MARKER boundaries; force-cut only if a single block exceeds limit."""
    positions = [0]
    idx = 0
    while True:
        pos = text.find(FILE_MARKER, idx)
        if pos == -1:
            break
        if pos == 0 or text[pos - 1] == "\n":
            positions.append(pos)
        idx = pos + 1
    positions.append(len(text))

    chunks, chunk_start, last_good = [], 0, 0
    for pos in positions[1:]:
        if pos - chunk_start <= limit:
            last_good = pos
        else:
            if last_good > chunk_start:
                chunks.append(text[chunk_start:last_good])
                chunk_start = last_good
                last_good = pos
            else:
                block = text[chunk_start:pos]
                while block:
                    piece = block[:limit]
                    if len(block) > limit:
                        piece += "\n[... CONTINUED IN NEXT CHUNK ...]"
                    chunks.append(piece)
                    block = block[limit:]
                chunk_start = pos
                last_good = pos

    if chunk_start < len(text):
        chunks.append(text[chunk_start:])
    return [c for c in chunks if c.strip()]


def run(in_path: Path, out_dir: Path, tag: str, limit: int = 90_000) -> dict:
    text        = in_path.read_text(encoding="utf-8", errors="replace")
    total_chars = len(text)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if total_chars <= limit:
        fname = f"{tag}_chunk_01_of_01.txt"
        header = (
            f"{'='*60}\n"
            f"  CHUNK 1 OF 1  —  {tag}\n"
            f"  Source     : {in_path.name}\n"
            f"  Generated  : {now}\n"
            f"  Characters : {total_chars:,}\n"
            f"{'='*60}\n\n"
        )
        (out_dir / fname).write_text(header + text + FILE_FOOTER, encoding="utf-8")
        return {"chunks": 1, "files": [fname], "total_chars": total_chars}

    pieces = _split(text, limit)
    total  = len(pieces)
    files  = []

    summary = [
        f"SPLIT SUMMARY — {tag}",
        "=" * 60,
        f"Source     : {in_path}",
        f"Generated  : {now}",
        f"Total chars: {total_chars:,}",
        f"Limit      : {limit:,}",
        f"Chunks     : {total}",
        "=" * 60, "",
    ]

    for i, chunk in enumerate(pieces, 1):
        fname = f"{tag}_chunk_{i:02d}_of_{total:02d}.txt"
        header = (
            f"{'='*60}\n"
            f"  CHUNK {i} OF {total}  —  {tag}\n"
            f"  Source     : {in_path.name}\n"
            f"  Generated  : {now}\n"
            f"  Characters : {len(chunk):,}\n"
            f"{'='*60}\n\n"
        )
        (out_dir / fname).write_text(header + chunk + FILE_FOOTER, encoding="utf-8")
        summary.append(f"  {fname}  —  {len(chunk):,} chars")
        files.append(fname)

    (out_dir / f"{tag}_chunks_summary.txt").write_text("\n".join(summary), encoding="utf-8")
    return {"chunks": total, "files": files, "total_chars": total_chars}
