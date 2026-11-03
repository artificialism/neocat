import argparse
import colorsys
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
COMMIT_COLORS = tuple(
    f"\033[{index}m"
    for index in (91, 92, 93, 94, 95, 96)
)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
HEADER = re.compile(r"^([0-9a-f]{40,64}) \d+ (\d+)(?: \d+)?$")
GIT_MODES = ("none", "git", "gb", "gcc")


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


def git_comments(blame):
    comments = {}
    last_line = {}
    seen = set()
    for number, (commit, _, summary) in sorted(blame.items()):
        previous = last_line.get(commit)
        if previous is None or number - previous > 3:
            label = summary if commit not in seen else ""
            comments[number] = (commit, label)
            seen.add(commit)
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


def get_commit_colors(commits):
    colors = {}
    used_rgb = set()
    for index, commit in enumerate(sorted(set(commits))):
        if index < len(COMMIT_COLORS):
            color = COMMIT_COLORS[index]
        else:
            hue = ((index - len(COMMIT_COLORS)) * 0.618033988749895) % 1
            rgb = colorsys.hsv_to_rgb(hue, 0.8, 1.0)
            red, green, blue = (round(channel * 255) for channel in rgb)
            value = (red << 16) | (green << 8) | blue
            while value in used_rgb:
                value = (value + 1) % 0x1000000
            used_rgb.add(value)
            red, green, blue = value >> 16, (value >> 8) & 255, value & 255
            color = f"\033[38;2;{red};{green};{blue}m"
        colors[commit] = color
    return colors


def get_columns(authors, comments, terminal_width, number_width, block_authors):
    labels = authors
    if block_authors:
        labels = {number: "┐ " + author if author else "" for number, author in authors.items()}
    author_width = get_author_width(labels, terminal_width, number_width)
    available = terminal_width - number_width - 2
    comment_width = 0
    if comments and terminal_width >= number_width + 16:
        wanted = min(max(wcswidth(text) for text in comments.values()), 60, terminal_width // 2)
        reserved_code = max(8, terminal_width // 2)
        budget = available - reserved_code - (author_width + 2 if author_width else 0) - 2
        if wanted and budget < min(12, wanted):
            author_width = 0
            budget = available - reserved_code - 2
        comment_width = min(wanted, max(0, budget))
    code_width = available
    if author_width:
        code_width -= author_width + 2
    if comment_width:
        code_width -= comment_width + 2
    return max(2, code_width), author_width, comment_width


def format_git_annotation(author, comment, color, author_width, comment_width, colored, colored_commits):
    annotation = ""
    if author_width:
        author = shorten(author, author_width)
        padding = author_width - wcswidth(author)
        if colored:
            if colored_commits and author:
                author = color + author[0] + CYAN + author[1:] + RESET
            else:
                author = CYAN + author + RESET
        annotation += author
        if comment_width:
            annotation += " " * (padding + 2)
    if comment_width:
        comment = shorten(comment, comment_width)
        if colored:
            comment = (color if colored_commits else DIM) + comment + RESET
        annotation += comment
    return annotation


def render(text, filename, args, authors, colored, output, comments=None, commits=None):
    text = text.replace("\r\n", "\n")
    text = safe_text(text).expandtabs(4)

    clean_authors = {}
    for number, author in authors.items():
        clean_authors[number] = safe_text(author)

    comments = comments or {}
    commits = commits or {}
    clean_comments = {
        number: safe_text(comment).expandtabs(4)
        for number, (_, comment) in comments.items()
    }
    commit_colors = {}
    if colored and args.git_comments_colored:
        commit_colors = get_commit_colors(
            set(commits.values()) | {commit for commit, _ in comments.values()}
        )

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

    block_authors = args.git_blocks or args.git_comments_colored
    code_width, author_width, comment_width = get_columns(
        clean_authors, clean_comments, terminal_width, number_width, block_authors
    )

    for number, tokens in enumerate(token_lines(text, lexer), 1):
        wrapped_rows = list(wrap_tokens(tokens, code_width))
        for row_index, (row, cells) in enumerate(wrapped_rows):
            label = ""
            author = ""
            comment = ""
            comment_color = DIM
            if colored and args.git_comments_colored and number in commits:
                comment_color = commit_colors[commits[number]]
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
                if number in comments and comment_width:
                    if colored and args.git_comments_colored and number not in commits:
                        comment_color = commit_colors[comments[number][0]]
                    if author == "│":
                        author = "┤"

            prefix = f"{label:>{number_width}}  "
            if colored:
                prefix = DIM + prefix + RESET
                source = format_tokens(row, formatter)
            else:
                source = "".join(value for _, value in row)

            suffix = ""
            if author_width or comment_width:
                suffix = " " * (code_width - cells + 2)
            suffix += format_git_annotation(
                author, comment, comment_color, author_width, comment_width,
                colored, args.git_comments_colored,
            )

            output.write(prefix + source + suffix + "\n")


def positive_int(value):
    number = int(value)
    if number < 8:
        raise argparse.ArgumentTypeError("width must be at least 8")
    return number


def config_path():
    directory = os.environ.get("XDG_CONFIG_HOME")
    root = Path(directory) if directory else Path.home() / ".config"
    return root / "neocat" / "config.json"


def load_default_mode():
    path = config_path()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict) or settings.get("git_mode") not in GIT_MODES:
            raise ValueError("git_mode must be one of: " + ", ".join(GIT_MODES))
        return settings["git_mode"]
    except FileNotFoundError:
        return "none"
    except (OSError, UnicodeError, ValueError) as error:
        print(f"neocat: ignoring {safe_text(str(path))}: {safe_text(str(error))}", file=sys.stderr)
        return "none"


def save_default_mode(mode):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"git_mode": mode}, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print source files directly into terminal scrollback.",
        epilog="Set the saved Git display: neocat --git set-default {none,git,gb,gcc}",
        allow_abbrev=False,
    )
    parser.add_argument("files", nargs="*", metavar="FILE", help="files to print; FILE N prints first N lines; - reads stdin")
    parser.add_argument("--git", "--g", action="store_true", help="show last Git author on each line")
    parser.add_argument("--git-blocks", "--gb", action="store_true", help="show authors once per block with guides, without commit subjects")
    parser.add_argument("--git-comments-colored", "-gcc", action="store_true", help="color all block guides by commit; show each subject once")
    parser.add_argument("-l", "--language", help="syntax language for files or stdin")
    parser.add_argument("--theme", default="dracula", help="Pygments theme (default: dracula)")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--width", type=positive_int, help="terminal width in columns (at least 8)")
    parser.add_argument("-p", "--plain", action="store_true", help="copy original bytes, like cat")
    parser.add_argument("--version", action="version", version="neocat 0.1.0")
    args = parser.parse_args(argv)
    if args.git and args.files and args.files[0] == "set-default":
        if len(args.files) != 2 or args.files[1] not in GIT_MODES or args.git_blocks or args.git_comments_colored:
            parser.error("use: neocat --git set-default {none,git,gb,gcc}")
        try:
            save_default_mode(args.files[1])
        except OSError as error:
            parser.exit(1, f"neocat: cannot save default: {safe_text(str(error))}\n")
        print(f"Default Git display: {args.files[1]}")
        return 0
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
    if decorated and not (args.git or args.git_blocks or args.git_comments_colored):
        mode = load_default_mode()
        args.git = mode == "git"
        args.git_blocks = mode == "gb"
        args.git_comments_colored = mode == "gcc"
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
            commits = {}
            if (args.git or args.git_blocks or args.git_comments_colored) and filename != "-":
                blame = git_blame(filename, content)
                authors = {number: info[1] for number, info in blame.items()}
                if args.git_comments_colored:
                    commits = {number: info[0] for number, info in blame.items()}
                    comments = git_comments(blame)
            render(text, filename, args, authors, colored, sys.stdout, comments, commits)
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
