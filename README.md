# neocat
Terminal file viewer with syntax highlighting, line numbers, and Git authors.

- Syntax highlighting powered by Pygments, with Dracula as the default theme.
- Cyan author annotations on the right with `--git`.
- Commit subjects at the start of each changed block with `--git-comments`.
- Line wrapping that keeps the full source visible.
- Plain, byte-for-byte output when piped or redirected.

## Usage

```sh
neocat file.py
neocat --git file.py
neocat --git-comments file.py
neocat --git --git-comments file.py
neocat file.py 10
neocat --git-comments file.py 10
neocat first.py second.py
cat file.py | neocat --language python
```

The language is detected from the filename. Use `--language` for stdin or to override detection. Unknown file extensions fall back to plain text.

Use `neocat FILE N` to print the first N source lines of a single file, or `neocat - N` for stdin. Wrapped display rows do not count as additional source lines. Zero prints nothing; counts larger than the file print the whole file. The limit also works with Git annotations, pipes, redirects, and `--plain`, preserving the selected lines' original bytes in plain output. With two positional arguments, a trailing integer is interpreted as the line count; use `./10` to refer to a second file literally named `10`.

## Installation

Requires Python 3.10+. Git is optional and only needed for author annotations.

Run these commands from the directory containing `neocat.py`:

```sh
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/neocat"
python3 -m venv "$HOME/.local/share/neocat/venv"
"$HOME/.local/share/neocat/venv/bin/python" -m pip install 'Pygments>=2.18,<3' 'wcwidth>=0.2.13,<1'
cp neocat.py "$HOME/.local/share/neocat/neocat.py"
cat > "$HOME/.local/bin/neocat" <<'EOF'
#!/bin/sh
exec "$HOME/.local/share/neocat/venv/bin/python" "$HOME/.local/share/neocat/neocat.py" "$@"
EOF
chmod +x "$HOME/.local/bin/neocat"
```

This installs a copy of the script and its dependencies for your user. You can move the source directory afterward.

### Add neocat to your PATH

If `~/.local/bin` is not already on your `PATH`, add this line to your shell configuration:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Use `~/.zshrc` for zsh or `~/.bashrc` for bash. For bash login sessions on macOS, also add it to `~/.bash_profile`.

## Options

| Option | Description |
| --- | --- |
| `--git`, `--blame` | Show the last Git author for each line. Disabled by default. |
| `--git-comments` | Show the commit subject on the first line of each block. Merge gaps of up to two lines. Disabled by default. |
| `-l`, `--language LANGUAGE` | Set the syntax highlighting language. |
| `--theme THEME` | Select a Pygments theme. Default: `dracula`. |
| `--color auto\|always\|never` | Control color output. Default: `auto`. |
| `--width COLUMNS` | Override the terminal width. Minimum: 8 columns. |
| `-p`, `--plain` | Copy the original bytes without formatting. |
| `--version` | Print the version. |
| `--help` | Show command-line help. |

Some examples:
```sh
neocat --theme monokai file.py
neocat --color never file.py
neocat --width 100 --git file.py
```

## Git annotations

`--git` shows the author of the last commit affecting each line, using the file contents at the time they are read. Uncommitted lines are labeled `Uncommitted`. 
Author names are shortened to fit the column, up to 24 symbols. The author column is hidden on very narrow terminals.

`--git-comments` shows the subject (first line of the commit message) on the right of the first line of each block attributed to that commit by Git blame. Consecutive sections from the same commit separated by one or two lines share one annotation. A gap of three or more lines starts a new block and repeats the subject. Intervening lines from other commits retain their own block annotations, even when commit subjects are identical.

This describes the latest commit affecting each current line, rather than every historical change. Uncommitted blocks are labeled `Uncommitted`. Comments can be used independently or together with `--git`; Git blame runs once per file. Subjects are shortened with an ellipsis to fit up to half the terminal width (at most 60 columns), and hidden on very narrow terminals. If both columns cannot fit, comments take priority over authors. Outside Git, for untracked files, or for stdin, Git annotations are omitted. Piped output and `--plain` still preserve the original bytes.

## Output behavior

Pipes and redirects preserve the original bytes:

```sh
neocat file.py > copy.py
neocat file.py | other-command
```

Use `--color always` to keep colors and line numbers in redirected output:

```sh
neocat --color always file.py > colored.md
```

`--plain` always copies the original bytes even with `--color always`. `--color never` disables colors but keeps line numbers in a terminal. A nonempty `NO_COLOR` or `TERM=dumb` disables automatic colors.
Formatted output expects UTF-8 text and displays control characters as visible escape sequences. Files containing NUL bytes require `--plain`. Formatting adds a newline after the final displayed row and reads one whole file into memory. Plain output streams bytes and preserves line endings.


## Uninstalling

```sh
rm "$HOME/.local/bin/neocat"
rm -rf "$HOME/.local/share/neocat"
```

## Related tools

- [bat](https://github.com/sharkdp/bat): syntax highlighting and Git change markers. Use `--paging=never` for inline output.
- [delta](https://github.com/dandavison/delta): formatting for Git diffs and blame output.
- [ccat](https://github.com/owenthereal/ccat): syntax highlighting for cat-style output.
