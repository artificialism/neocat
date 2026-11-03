# neocat
Terminal file viewer with syntax highlighting, line numbers, and Git authors.

- Syntax highlighting powered by Pygments, with Dracula as the default theme.
- Cyan author annotations on the right with `--git`.
- Commit-colored guides and a subject at each commit’s first appearance with `-gcc`.
- Line wrapping that keeps the full source visible.
- Plain, byte-for-byte output when piped or redirected.

## Usage

```sh
neocat file.py
neocat --git file.py
neocat --gb file.py
neocat -gcc file.py
neocat file.py 10
neocat -gcc file.py 10
neocat first.py second.py
cat file.py | neocat --language python
```

The language is detected from the filename. Use `--language` for stdin or to override detection. Unknown file extensions fall back to plain text.

Use `neocat FILE N` to print the first N source lines of a single file, or `neocat - N` for stdin. Wrapped display rows do not count as additional source lines. Zero prints nothing; counts larger than the file print the whole file. The limit also works with Git annotations, pipes, redirects, and `--plain`, preserving the selected lines' original bytes in plain output. With two positional arguments, a trailing integer is interpreted as the line count; use `./10` to refer to a second file literally named `10`.

### Default Git display

Save the Git display used when no Git flag is supplied:

```sh
neocat --git set-default gcc   # colored commit guides and subjects
neocat --git set-default gb    # author blocks
neocat --git set-default git   # author on every line
neocat --git set-default none  # turn off the saved Git display
```

After selecting `gcc`, `neocat file.py` uses the same display as `neocat -gcc file.py`. Explicit Git flags override the saved choice: `neocat --g file.py` still shows authors on every line. The `--g` alias also works for `set-default`. Settings are stored in `$XDG_CONFIG_HOME/neocat/config.json`, or `~/.config/neocat/config.json` when that environment variable is unset. No default is saved until you run `set-default`. Ordinary pipes, redirects, and `--plain` continue to preserve the selected source bytes; `--color always` enables formatted output and the saved display even when redirected. Invalid settings produce a warning and fall back to no Git annotations; explicit Git flags bypass the settings file.

`none` resets only the saved Git display: syntax highlighting and line numbers remain enabled in formatted output. Each `set-default` command saves the choice and exits without printing a file.

## Installation

Requires Python 3.10+. Git is optional and only needed for Git annotations.

Run from the directory containing `neocat.py`:

```sh
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/neocat"
python3 -m venv "$HOME/.local/share/neocat/venv"
"$HOME/.local/share/neocat/venv/bin/python" -m pip install 'Pygments>=2.18,<3' 'wcwidth>=0.2.13,<1'
cp neocat.py "$HOME/.local/share/neocat/neocat.py"
cat > "$HOME/.local/share/neocat/launcher" <<'EOF'
#!/bin/sh
exec "$HOME/.local/share/neocat/venv/bin/python" "$HOME/.local/share/neocat/neocat.py" "$@"
EOF
chmod +x "$HOME/.local/share/neocat/launcher"
ln -sf "$HOME/.local/share/neocat/launcher" "$HOME/.local/bin/neocat"
```

Add `~/.local/bin` to your PATH if necessary:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Save that line in `~/.zshrc` for zsh or `~/.bashrc` for bash, then restart your shell.

To update an installation, copy the current script again:

```sh
cp neocat.py "$HOME/.local/share/neocat/neocat.py"
```

For development, run the source directly with its dependencies installed:

```sh
python3 neocat.py file.py
```

## Options

| Option | Description |
| --- | --- |
| `--git`, `--g` | Show the last Git author on every source line. Overrides the saved default. |
| `--git-blocks`, `--gb` | Show authors once per continuous block with guides, without commit subjects. Overrides the saved default. |
| `--git-comments-colored`, `-gcc` | Color all block guides by commit; show each commit subject once per file, without hashes. Overrides the saved default. |
| `--git set-default none\|git\|gb\|gcc` | Save the default Git display and exit. Also accepts `--g set-default`. |
| `-l`, `--language LANGUAGE` | Set the syntax highlighting language. |
| `--theme THEME` | Select a Pygments theme. Default: `dracula`. |
| `--color auto\|always\|never` | Control color output. Default: `auto`. |
| `--width COLUMNS` | Override the terminal width. Minimum: 8 columns. |
| `-p`, `--plain` | Copy the original bytes without formatting. |
| `--version` | Print the version. |
| `-h`, `--help` | Show command-line help. |

Some examples:
```sh
neocat --theme monokai file.py
neocat --color never file.py
neocat --width 100 --git file.py
```

## Git annotations

A block is a continuous section of code attributed to one author. In `-gcc`, the guide colors distinguish different commits within these author blocks.

`--git` (or `--g`) shows the author of the last commit affecting every source line, using the file contents at the time they are read. Names repeat on each source line without block guides. Uncommitted lines are labeled `Uncommitted`.
Author names are shortened to fit the column, up to 24 symbols. The author column is hidden on very narrow terminals.
`--git-blocks` (or `--gb`) groups authors without commit subjects: the name appears once per continuous author block. When authors alternate, each change repeats the name. Author blocks are marked with `┐ Name` on the first row, `│` on continuation rows, and `┘` on the last row. Single-row blocks use `─ Name`. The guide also follows wrapped code rows and ends at the last displayed line when a line limit is used. `-gcc` uses the same author blocks and adds commit colors and subjects.

`--git-comments-colored` (or `-gcc`) shows no commit hashes. It shows each subject only at the commit's first appearance in the file. All guide markers belonging to a source line use that line's commit color, including wrapped continuation rows and closing corners. The subject shares that color; returning sections keep the color without repeating the subject. The first six commits use the terminal’s classic bright colors (red, green, yellow, blue, magenta, cyan). Additional commits receive distinct generated RGB colors; these require true-color terminal support. Disabling color still shows subjects once without hashes. Sections starting inside an author block use a left branch `┤`; the final row keeps `┘`. Uncommitted changes use their own color and one `Uncommitted` annotation.

This describes the latest commit affecting each current line, rather than every historical change. Uncommitted blocks are labeled `Uncommitted`. `--gb` and `-gcc` include authors automatically and take priority over the per-line display of `--git` or `--g`. Combining `--gb` and `-gcc` keeps commit colors and subjects. Git blame runs once per file. Subjects are shortened with an ellipsis to fit the available space (at most 60 columns), and hidden on very narrow terminals. `-gcc` reserves at least half the terminal width for code when annotations are shown. If both annotation columns cannot fit, comments take priority over authors. Outside Git, for untracked files, or for stdin, Git annotations are omitted. Piped output and `--plain` still preserve the original bytes.

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
