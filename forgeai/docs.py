"""Document loading, profiling and chunking for arbitrary (unseen) folders."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

SUPPORTED = {".pdf", ".md", ".txt", ".csv", ".tsv", ".html", ".htm", ".json", ".docx"}


@dataclass
class Document:
    name: str  # file name - used as the citation id
    path: str
    kind: str  # pdf | text | table
    text: str
    pages: int = 1
    columns: list = field(default_factory=list)
    rows: int = 0

    def meta(self) -> dict:
        d = asdict(self)
        d.pop("text")
        d["chars"] = len(self.text)
        d["words"] = len(self.text.split())
        return d


@dataclass
class Chunk:
    id: str  # "<doc>#<n>"
    doc: str
    text: str
    section: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- loading
def _read_pdf(p: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    r = PdfReader(str(p))
    pages = [(pg.extract_text() or "") for pg in r.pages]
    return "\n\n".join(pages), len(pages)


def _read_docx(p: Path) -> str:
    import zipfile

    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _read_table(p: Path) -> tuple[str, list, int]:
    raw = p.read_text(encoding="utf-8", errors="ignore")
    dialect = "excel-tab" if p.suffix.lower() == ".tsv" else "excel"
    rows = list(csv.reader(io.StringIO(raw), dialect=dialect))
    if not rows:
        return "", [], 0
    header, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    lines = []
    for r in body:
        lines.append("; ".join(f"{h}: {v}" for h, v in zip(header, r) if v.strip()))
    return "\n".join(lines), header, len(body)


def load_folder(folder: str | Path) -> list[Document]:
    folder = Path(folder)
    docs: list[Document] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUPPORTED or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        try:
            if ext == ".pdf":
                text, n = _read_pdf(p)
                docs.append(Document(p.name, str(p), "pdf", _clean(text), pages=n))
            elif ext in (".csv", ".tsv"):
                text, cols, n = _read_table(p)
                docs.append(Document(p.name, str(p), "table", text, columns=cols, rows=n))
            elif ext == ".docx":
                docs.append(Document(p.name, str(p), "text", _clean(_read_docx(p))))
            elif ext in (".html", ".htm"):
                t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", p.read_text(errors="ignore"), flags=re.S)
                docs.append(Document(p.name, str(p), "text", _clean(re.sub(r"<[^>]+>", " ", t))))
            else:
                docs.append(Document(p.name, str(p), "text", _clean(p.read_text(errors="ignore"))))
        except Exception as e:  # a broken file must not kill an unattended run
            print(f"[docs] skipping {p.name}: {e}")
    return [d for d in docs if d.text.strip()]


def _clean(t: str) -> str:
    t = t.replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# --------------------------------------------------------------------------- chunking
_HEADING = re.compile(r"^(#{1,6}\s+.+|\d+(\.\d+)*\.?\s+[A-Z][^\n]{2,80}|[A-Z][A-Z &/\-]{3,60})$")


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split on headings (markdown, numbered '3.2 Title', ALL CAPS lines)."""
    sections, title, buf = [], "", []
    for line in text.split("\n"):
        s = line.strip()
        if s and len(s) < 90 and _HEADING.match(s):
            if buf:
                sections.append((title, "\n".join(buf).strip()))
            title, buf = s.lstrip("#").strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((title, "\n".join(buf).strip()))
    return [(t, b) for t, b in sections if b]


def _pack(words: list[str], size: int, overlap: int) -> list[str]:
    if len(words) <= size:
        return [" ".join(words)]
    out, step = [], max(1, size - overlap)
    for s in range(0, len(words), step):
        out.append(" ".join(words[s : s + size]))
        if s + size >= len(words):
            break
    return out


def chunk_documents(docs: list[Document], strategy: str = "section", size: int = 220, overlap: int = 40, rows_per_chunk: int = 1) -> list[Chunk]:
    chunks: list[Chunk] = []
    for d in docs:
        n = 0
        if d.kind == "table":
            lines = d.text.split("\n")
            for s in range(0, len(lines), rows_per_chunk):
                chunks.append(Chunk(f"{d.name}#{n}", d.name, "\n".join(lines[s : s + rows_per_chunk]), "row"))
                n += 1
            continue
        if strategy == "section":
            for title, body in _split_sections(d.text) or [("", d.text)]:
                for piece in _pack(body.split(), size, overlap):
                    # contextual header: helps BM25 and gives the model provenance
                    text = f"[{d.name} > {title}]\n{piece}" if title else f"[{d.name}]\n{piece}"
                    chunks.append(Chunk(f"{d.name}#{n}", d.name, text, title))
                    n += 1
        else:  # fixed windows
            for piece in _pack(d.text.split(), size, overlap):
                chunks.append(Chunk(f"{d.name}#{n}", d.name, f"[{d.name}]\n{piece}", ""))
                n += 1
    return chunks


def profile(docs: list[Document]) -> dict:
    """Cheap deterministic stats used by the generator to pick chunking params."""
    sec_lens = []
    for d in docs:
        if d.kind != "table":
            sec_lens += [len(b.split()) for _, b in _split_sections(d.text)]
    sec_lens.sort()
    median = sec_lens[len(sec_lens) // 2] if sec_lens else 0
    return {
        "n_docs": len(docs),
        "kinds": sorted({d.kind for d in docs}),
        "total_words": sum(len(d.text.split()) for d in docs),
        "has_tables": any(d.kind == "table" for d in docs),
        "table_files": [d.name for d in docs if d.kind == "table"],
        "median_section_words": median,
        "n_sections": len(sec_lens),
    }


def find_doc(docs: list[Document], name: str) -> Optional[Document]:
    for d in docs:
        if d.name == name:
            return d
    return None
