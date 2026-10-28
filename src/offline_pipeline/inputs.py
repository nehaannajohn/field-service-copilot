"""Build model inputs for one file: a PDF part, or text parts split to fit the model's output limit."""
import base64
import csv
import io
import json
from dataclasses import dataclass
from email import message_from_bytes, policy
from html.parser import HTMLParser
from pathlib import Path

import docx

from common.config import load_config


@dataclass
class ModelInput:
    part: int          # 1-based part number within the file
    total_parts: int
    content: dict      # one Responses API content part (input_file or input_text)


class Unreadable(Exception):
    """File can't be sent: zero bytes, or text that can't be decoded."""


def build_inputs(path: Path) -> list[ModelInput]:
    data = path.read_bytes()
    if not data:
        raise Unreadable("zero bytes")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        b64 = base64.b64encode(data).decode()
        return [ModelInput(1, 1, {"type": "input_file", "filename": path.name,
                                  "file_data": f"data:application/pdf;base64,{b64}"})]
    if suffix == ".docx":
        texts = [docx_text(path)]
    elif suffix in (".html", ".htm"):
        texts = split_text(html_text(decode(data)), ".txt")
    elif suffix == ".eml":
        texts = split_text(eml_text(data), ".txt")
    else:
        texts = split_text(decode(data), suffix)
    return [ModelInput(i, len(texts), {"type": "input_text", "text": t}) for i, t in enumerate(texts, 1)]


def decode(data: bytes) -> str:
    for encoding in ("utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise Unreadable("text could not be decoded")


def docx_text(path: Path) -> str:
    """Paragraphs with heading levels as '#' prefixes, then tables as ' | '-joined rows."""
    try:
        document = docx.Document(path)
    except Exception as e:
        raise Unreadable(f"DOCX could not be opened: {type(e).__name__}") from e
    lines = []
    for p in document.paragraphs:
        if not p.text.strip():
            continue
        style = p.style.name if p.style is not None else ""
        level = style.removeprefix("Heading ")
        lines.append(f"{'#' * int(level)} {p.text}" if level.isdigit() else p.text)
    for table in document.tables:
        lines.append("")
        lines.extend(" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows)
    return "\n".join(lines)


class _HTMLText(HTMLParser):
    """Visible text of an HTML page: headings as '#' lines, list items as '- ' lines, table cells joined by ' | '."""
    SKIP = {"script", "style", "head"}
    BLOCKS = {"p", "div", "br", "ul", "ol", "table", "pre", "blockquote", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.first_cell = [], 0, True

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "tr":
            self.out.append("\n")
            self.first_cell = True
        elif tag in ("td", "th"):
            if not self.first_cell:
                self.out.append(" | ")
            self.first_cell = False
        elif tag in self.BLOCKS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS or tag.startswith("h") and tag[1:].isdigit():
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(" ".join(data.split()) + (" " if data[-1:].isspace() else ""))


def html_text(html: str) -> str:
    parser = _HTMLText()
    parser.feed(html)
    lines = [line.strip() for line in "".join(parser.out).splitlines()]
    return "\n".join(line for line in lines if line)


def eml_text(data: bytes) -> str:
    """Headers plus the plain-text body (or the HTML body converted to text). Attachments are listed by name."""
    message = message_from_bytes(data, policy=policy.default)
    headers = [f"{name}: {message[name]}" for name in ("From", "To", "Cc", "Date", "Subject") if message[name]]
    body_part = message.get_body(preferencelist=("plain", "html"))
    if body_part is None:
        raise Unreadable("email has no text body")
    body = body_part.get_content()
    if body_part.get_content_subtype() == "html":
        body = html_text(body)
    attachments = [p.get_filename() for p in message.iter_attachments() if p.get_filename()]
    if attachments:
        headers.append("Attachments: " + ", ".join(attachments))
    return "\n".join(headers) + "\n\n" + body


def split_text(text: str, suffix: str) -> list[str]:
    ingest = load_config()["ingest"]
    limit, max_records = ingest["max_input_chars"], ingest["max_records_per_part"]
    if suffix == ".csv":
        return split_csv(text, limit, max_records)
    if suffix == ".json":
        return split_json(text, limit, max_records)
    if len(text) <= limit:
        return [text]
    parts, current = [], []
    for line in text.splitlines():
        if current and len("\n".join(current + [line])) > limit:
            parts.append("\n".join(current))
            current = []
        current.append(line)
    parts.append("\n".join(current))
    return parts


def split_csv(text: str, limit: int, max_records: int) -> list[str]:
    """Split by real CSV rows (quoted line breaks stay inside their row), repeating the header."""
    dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
    header, *rows = list(csv.reader(io.StringIO(text), dialect))
    parts, current = [], []

    def render(batch):
        out = io.StringIO()
        csv.writer(out, delimiter=dialect.delimiter, lineterminator="\n").writerows([header, *batch])
        return out.getvalue()

    for row in rows:
        if current and (len(current) >= max_records or len(render(current + [row])) > limit):
            parts.append(render(current))
            current = []
        current.append(row)
    parts.append(render(current))
    return parts


def split_json(text: str, limit: int, max_records: int) -> list[str]:
    """Split the largest list of objects, wherever it is in the JSON, into parts under both caps."""
    data = json.loads(text)
    records = largest_record_list(data)
    if not records:
        return [text]
    parts, current = [], []
    for record in records:
        too_long = len(json.dumps(current + [record], ensure_ascii=False, indent=1)) > limit
        if current and (len(current) >= max_records or too_long):
            parts.append(json.dumps(current, ensure_ascii=False, indent=1))
            current = []
        current.append(record)
    parts.append(json.dumps(current, ensure_ascii=False, indent=1))
    return parts


def largest_record_list(node) -> list:
    """The longest list of dicts anywhere in the structure (e.g. Salesforce 'records', Teams 'value')."""
    best = node if isinstance(node, list) and node and all(isinstance(x, dict) for x in node) else []
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else []
    for child in children:
        candidate = largest_record_list(child)
        if len(candidate) > len(best):
            best = candidate
    return best
