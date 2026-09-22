## petri

Tooling for Stanford SC.

<!-- - `.bashrc` - My tooling
- `.defaultrc` - FAIR's pre-installed `.bashrc`
- `slurm/` - Slurm tooling (all claude slop)

The `slurm/` tooling gives tools like `tt`, `ttt`, `sp`! E.g.

<p align="center">
<img width="600" src="https://github.com/user-attachments/assets/cb74696b-ffb4-4118-9a89-9e68b9c15fe4" />
</p> -->

### quick start

```sh
cd ~
git clone git@github.com:davidheineman/petri.git

# append to ~/.bashrc
cat <<'EOF' >> ~/.bashrc

source ~/fairdev/.bashrc
EOF

# run devtools setup
./setup_devtools.sh

# install fb vscode extensions
xargs -I {} cursor-server --install-extension {} < code_extensions.txt

# pull my personal claude rules
mkdir -p ~/.claude/skills/david
curl -L https://raw.githubusercontent.com/davidheineman/dotfiles/refs/heads/main/.cursor/rules.mdc -o ~/.claude/skills/david/SKILL.md
```

### shortcuts

```sh
# overridden vscode shortcuts (you can see with @source:user)
code-compose.chat.toggle -> CMD + I
CodeCompose: Show Inline Chat -> CMD + K

Terminal: Split Terminal
Terminal: Rename -> CMD + T
Toggle Word Wrap -> CTRL + Z
Show Prev Window Tab -> CTRL + CMD + LEFT
Show Next Window Tab -> CTRL + CMD + RIGHT
Trim Trailing Whitespace -> ALT + V
```