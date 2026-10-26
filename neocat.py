import argparse
import os
import re
import shutil
import subprocess
import sys
from itertools import islice
from pathlib import Path

from pygments import format as format_tokens
from pygments.formatters import TerminalTrueColorFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, get_lexer_for_filename
from pygments.util import ClassNotFound
from wcwidth import wcwidth, wcswidth

RESET = "\033[0m"
DIM = "\033[2;90m"
CYAN = "\033[36m"
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
HEADER = re.compile(r"^([0-9a-f]{40,64}) \d+ (\d+)(?: \d+)?$")


def safe_text(text):
    return CONTROL.sub(lambda match: f"\\x{ord(match[0]):02x}", text)


def git_blame(path, content):
    path = Path(path).resolve()
    try:
        result = subprocess.run(
            [
                "git", "-C", str(path.parent), "-c", "core.quotePath=false",
                "blame", "--line-porcelain", "--contents", "-", "--", path.name,
            ],
            input=content,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    lines = {}
    number = None
    author = ""
    summary = ""
    uncommitted = False
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        match = HEADER.match(line)
        if match:
            number = int(match[2])
            commit_hash = match[1]
            uncommitted = int(commit_hash, 16) == 0
        elif line.startswith("author "):
            author = safe_text(line[7:])
        elif line.startswith("summary "):
            summary = safe_text(line[8:])
        elif line.startswith("\t") and number is not None:
            lines[number] = (
                commit_hash,
                "Uncommitted" if uncommitted else author,
                "Uncommitted" if uncommitted else summary,
            )
    return lines


def git_authors(path, content):
    return {number: info[1] for number, info in git_blame(path, content).items()}


def git_comments(blame):
    comments = {}
    last_line = {}
    for number, (commit, _, summary) in sorted(blame.items()):
        previous = last_line.get(commit)
        if previous is None or number - previous > 3:
            comments[number] = summary
        last_line[commit] = number
    return comments


def token_lines(text, lexer):
    row = []
    for _, token, value in lexer.get_tokens_unprocessed(text):
        parts = value.split("\n")
        for index, part in enumerate(parts):
            if index:
                yield row
                row = []
            if part:
                row.append((token, part))
    if row:
        yield row


def wrap_tokens(tokens, width):
    row = []
    cells = 0
    for token, value in tokens:
        for char in value:
            size = max(0, wcwidth(char))
            if row and cells + size > width:
                yield row, cells
                row = []
                cells = 0
            if row and row[-1][0] == token:
                row[-1] = (token, row[-1][1] + char)
            else:
                row.append((token, char))
            cells += size
    yield row, cells


def shorten(text, width):
    if wcswidth(text) <= width:
        return text
    result = ""
    cells = 0
    for char in text:
        size = max(0, wcwidth(char))
        if cells + size > width - 1:
            break
        result += char
        cells += size
    return result + "…"


def select_lexer(filename, text, language):
    try:
        if language:
            return get_lexer_by_name(language)
        return get_lexer_for_filename(filename, text)
    except ClassNotFound:
        if language:
            raise ValueError(f"unknown language: {language}") from None
        return TextLexer()


def get_author_width(authors, terminal_width, number_width):
    if terminal_width < number_width + 16:
        return 0

    longest_name = 0
    for author in authors.values():
        name_width = wcswidth(author)
        longest_name = max(longest_name, name_width)

    column_limit = terminal_width // 3
    return min(longest_name, 24, column_limit)


def render(text, filename, args, authors, colored, output, comments=None):
    text = text.replace("\r\n", "\n")
    text = safe_text(text).expandtabs(4)

    clean_authors = {}
    for number, author in authors.items():
        clean_authors[number] = safe_text(author)

    clean_comments = {
        number: safe_text(comment).expandtabs(4)
        for number, comment in (comments or {}).items()
    }

    lexer = select_lexer(filename, text, args.language)
    formatter = None
    if colored:
        formatter = TerminalTrueColorFormatter(style=args.theme)

    line_count = text.count("\n")
    if text and not text.endswith("\n"):
        line_count += 1
    number_width = len(str(max(1, line_count)))

    terminal_width = args.width
    if not terminal_width:
        terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns

    block_authors = args.git_blocks or args.git_comments
    author_labels = clean_authors
    if block_authors:
        author_labels = {
            number: "┐ " + author if author else ""
            for number, author in clean_authors.items()
        }
    author_width = get_author_width(author_labels, terminal_width, number_width)
    comment_width = 0
    if clean_comments and terminal_width >= number_width + 16:
        comment_width = min(
            max(wcswidth(comment) for comment in clean_comments.values()),
            60, terminal_width // 2,
        )
    code_width = terminal_width - number_width - 2
    if author_width:
        code_width -= author_width + 2
    if comment_width:
        code_width -= comment_width + 2
    # Prefer the requested commit comments when both columns cannot fit.
    if comment_width and code_width < 8 and author_width:
        code_width += author_width + 2
        author_width = 0
    code_width = max(2, code_width)

    for number, tokens in enumerate(token_lines(text, lexer), 1):
        wrapped_rows = list(wrap_tokens(tokens, code_width))
        for row_index, (row, cells) in enumerate(wrapped_rows):
            label = ""
            author = ""
            comment = ""
            current_author = clean_authors.get(number, "")
            continues = (
                row_index < len(wrapped_rows) - 1
                or (number < line_count and current_author == clean_authors.get(number + 1))
            )
            if current_author and block_authors:
                starts = row_index == 0 and current_author != clean_authors.get(number - 1)
                if starts:
                    author = ("┐ " if continues else "─ ") + current_author
                else:
                    author = "│" if continues else "┘"
            elif row_index == 0:
                author = current_author
            if row_index == 0:
                label = str(number)
                comment = clean_comments.get(number, "")

            prefix = f"{label:>{number_width}}  "
            if colored:
                prefix = DIM + prefix + RESET
                source = format_tokens(row, formatter)
            else:
                source = "".join(value for _, value in row)

            suffix = ""
            if author_width or comment_width:
                suffix = " " * (code_width - cells + 2)
            if author_width:
                author = shorten(author, author_width)
                author_padding = author_width - wcswidth(author)
                if colored:
                    author = CYAN + author + RESET
                suffix += author
                if comment_width:
                    suffix += " " * (author_padding + 2)
            if comment_width:
                comment = shorten(comment, comment_width)
                if colored:
                    comment = DIM + comment + RESET
                suffix += comment

            output.write(prefix + source + suffix + "\n")


def positive_int(value):
    number = int(value)
    if number < 8:
        raise argparse.ArgumentTypeError("width must be at least 8")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print source files directly into terminal scrollback.")
    parser.add_argument("files", nargs="*", metavar="FILE", help="files to print; FILE N prints first N lines; - reads stdin")
    parser.add_argument("--git", "--blame", action="store_true", help="show last Git author on each line")
    parser.add_argument("--git-blocks", "--gb", action="store_true", help="show authors once per block with guides, without commit subjects")
    parser.add_argument("--git-comments", "--gc", action="store_true", help="show authors with block guides and commit subjects (merge subject gaps up to 2 lines)")
    parser.add_argument("-l", "--language", help="syntax language for files or stdin")
    parser.add_argument("--theme", default="dracula", help="Pygments theme (default: dracula)")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--width", type=positive_int, help="terminal width in columns (at least 8)")
    parser.add_argument("-p", "--plain", action="store_true", help="copy original bytes, like cat")
    parser.add_argument("--version", action="version", version="neocat 0.1.0")
    args = parser.parse_args(argv)
    line_limit = None
    if len(args.files) == 2 and re.fullmatch(r"[+-]?[0-9]+", args.files[-1]):
        try:
            line_limit = int(args.files.pop())
        except ValueError:
            parser.error("line count is too large")
        if line_limit < 0:
            parser.error("line count must be nonnegative")
    if not args.files:
        if sys.stdin.isatty():
            parser.error("provide a file or pipe input; use '-' to read stdin explicitly")
        if not sys.stdin.buffer.peek(1):
            parser.error("provide a file or pipe input; stdin is empty")

    terminal = sys.stdout.isatty()
    decorated = not args.plain and (terminal or args.color == "always")
    auto_color = (
        args.color == "auto"
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM") != "dumb"
    )
    colored = decorated and (args.color == "always" or auto_color)
    status = 0
    files = args.files
    if not files:
        files = ["-"]

    for filename in files:
        try:
            if filename == "-":
                stream = sys.stdin.buffer
            else:
                stream = open(filename, "rb")
            try:
                if not decorated:
                    if line_limit is None:
                        shutil.copyfileobj(stream, sys.stdout.buffer)
                    else:
                        for line in islice(stream, line_limit):
                            sys.stdout.buffer.write(line)
                    continue
                if line_limit is None:
                    content = stream.read()
                else:
                    content = b"".join(islice(stream, line_limit))
            finally:
                if filename != "-":
                    stream.close()
            text = content.decode("utf-8")
            if "\x00" in text:
                raise ValueError("binary file; use --plain to copy its bytes")
            authors = {}
            comments = {}
            if (args.git or args.git_blocks or args.git_comments) and filename != "-":
                blame = git_blame(filename, content)
                authors = {number: info[1] for number, info in blame.items()}
                if args.git_comments:
                    comments = git_comments(blame)
            render(text, filename, args, authors, colored, sys.stdout, comments)
        except BrokenPipeError:
            raise
        except IsADirectoryError:
            print(f"neocat: {safe_text(filename)}: is a directory; provide a file", file=sys.stderr)
            status = 1
        except (OSError, UnicodeError, ValueError, ClassNotFound) as error:
            print(f"neocat: {safe_text(filename)}: {safe_text(str(error))}", file=sys.stderr)
            status = 1
    return status


def entrypoint():
    try:
        return main()
    except BrokenPipeError:
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(entrypoint())
