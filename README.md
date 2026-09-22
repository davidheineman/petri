## petri

Tooling for Stanford SC.

<!-- <p align="center">
<img width="600" src="https://github.com/user-attachments/assets/cb74696b-ffb4-4118-9a89-9e68b9c15fe4" />
</p> -->

### getting into cluster

```sh
# first-time login use kinit
# https://support.cs.stanford.edu/hc/en-us/articles/360000042706-Setting-up-password-less-SSH-from-your-Mac-to-CS-systems
export KRB_PASSWORD='YOUR_CSID_PASSWORD'
SSHPASS="$KRB_PASSWORD" sshpass -e ssh dhei@sc.stanford.edu

# (on remote) add your SSH pubkey
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
# (paste in your pubkey)
chmod 600 ~/.ssh/authorized_keys

# (on remote) launch cpu session (7 day timeout)
sbatch --account=nlp --partition=sc-loprio --job-name="👋-dhei-interact-👋" --wrap="sleep infinity"
```

Then update local `~/.ssh/config` with hostnames (e.g. for `iliad1`):

```sh
Host sc
    HostName sc.stanford.edu
    User dhei
    IdentityFile ~/.ssh/id_rsa
    IdentitiesOnly yes
    AddKeysToAgent yes
    UseKeychain yes

Host interact
    HostName iliad1.stanford.edu
    User dhei
    IdentityFile ~/.ssh/id_rsa
    IdentitiesOnly yes
    AddKeysToAgent yes
    UseKeychain yes
```

### quick start

```sh
cd ~
git clone git@github.com:davidheineman/petri.git

# append to ~/.bashrc
cat <<'EOF' >> ~/.bashrc

source ~/petri/.bashrc
EOF

# run devtools setup
chmod +x ./setup_devtools.sh
./setup_devtools.sh

# install cursor extensions
xargs -I {} cursor --install-extension {} < code_extensions.txt

# pull my personal claude rules
mkdir -p ~/.claude/skills/david
curl -L https://raw.githubusercontent.com/davidheineman/dotfiles/refs/heads/main/.cursor/rules.mdc -o ~/.claude/skills/david/SKILL.md
```

### slurm tooling

```sh
smiso # miso queue (40 × h200)
nlp # all nlp qeueues
sp # job priority
si # attach to job

# other queues
sjag # 104 (a6000, rtx6000ada, 3090, a5000, titanrtx, titanv)
ssphinx # 86 (a100, a6000)
sjohn # 0 (cpu only)
slo # (623 preemptible queue)
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
