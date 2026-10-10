# neocat

Print files with syntax highlighting, dim line numbers, and optional cyan Git authors on the right. Output stays in your terminal scrollback.

## Installation

Requires Python 3.10+ with `venv` support. Git is needed only for `--git`.

**macOS** (with [Homebrew](https://brew.sh/)):

```sh
brew install python git
```

**Ubuntu / Debian:**

```sh
sudo apt update
sudo apt install python3 python3-venv git
```

**Fedora:**

```sh
sudo dnf install python3 python3-pip git
```

From the directory containing `neocat.py`:

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

Add this line to `~/.zshrc` (zsh) or `~/.bashrc` (bash). For bash login sessions on macOS, use `~/.bash_profile`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

For fish, run `fish_add_path "$HOME/.local/bin"` instead.

Open a new terminal and run `neocat --version`. The command works from any directory without activating an environment.

## Usage

```sh
neocat file.py
neocat --git file.py
neocat --theme monokai file.py
cat file.py | neocat --language python
neocat --help
```

The default theme is Dracula. `--git` shows the last author for each line; uncommitted lines show `Uncommitted`.

Piped or redirected output preserves the original bytes. Use `--color always` to keep formatting or `--plain` to disable it.

Running without a file or with empty piped input reports an error. Directories are rejected. Use `neocat -` to read stdin explicitly.

## Update

From the directory containing the updated script:

```sh
cp neocat.py "$HOME/.local/share/neocat/neocat.py"
```

## Uninstall

```sh
rm "$HOME/.local/bin/neocat"
rm -rf "$HOME/.local/share/neocat"
```
