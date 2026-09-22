# (%.XXj controls name size)
alias sq='squeue --user dhei --format="%.18i %.12P %.20j %.8u %.8T %.10M %.6D %R"'
alias sc='scancel'
alias scall='scancel -u dhei'
alias saccts='sacctmgr show qos format=name%30,GrpTRES%20,priority' # check all accounts on the cluster

alias sqw='watch -n 1 squeue -u dhei'

# check usage in our accounts
alias susage='squeue --Format=JobID,UserName,Account,QOS,NumNodes,tres-per-job:.30,tres-per-node:.50,Reason:.30 --qos miso,miso-lo,miso-interactive'

# show stats
alias ss='sstat -j' # <job-id>

# https://github.com/davidheineman/beaker_image/blob/main/src/.bashrc
alias uvinit='uv venv --python 3.12 && source .venv/bin/activate'
alias uva='source .venv/bin/activate'
alias uvinstall='uv pip install -r requirements.txt'

# Easy create conda env
condacreate() {
    env_name=$1
    conda create -y -n "$env_name"
    conda install -y -n "$env_name" pip
    conda install -y -n "$env_name" python=3.10
    conda activate "$env_name"
}

# disable pip (to encourage uv usage)
# pip_path=$(which pip)
# [ -n "$pip_path" ] && sudo mv "$pip_path" "$(dirname "$pip_path")/pipforce" # <- breaks if you don't have default sudo permissions!
alias pip="uv pip" # Error: pip is disabled (use uv/uvinit/uva instead, its better). if you need to use it, call pipforce

alias nv='nvidia-smi' # | lolcat
alias nvw="watch -n 1 nvidia-smi"

alias code="code-fb" # can only use code-fb and cursor on fair-sc

# https://code.claude.com/docs/en/changelog
# CLAUDE_CODE_VERSION_OVERRIDE=2.1.234 
alias claude="claude --dangerously-skip-permissions --effort high --model claude-opus-5"
alias cresume="claude --resume"
alias ct='tmux new-session "bash -ic claude"'

# disable new claude container env (the new one doesn't allow /fast mode)
export LAUNCHER=0

alias ta='tmux attach -t'
alias t='tmux'

issue() { # open issue folder
    code ~/.cache/deviousutils/issue-watcher/worktrees/issue-$*
}

# >>> conda initialize (lazy) >>>
# Defer conda init until first use to keep shell startup fast.
export PATH="/opt/conda/bin:$PATH"
conda() {
    unset -f conda
    __conda_setup="$('/opt/conda/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
        . "/opt/conda/etc/profile.d/conda.sh"
    fi
    unset __conda_setup
    conda "$@"
}
# <<< conda initialize (lazy) <<<

# CLI color coding
PS1_RESET='\[\e[0m\]'
PS1_BOLD='\[\e[1m\]'
PS1_DIM='\[\e[2m\]'
PS1_UNDERLINE='\[\e[4m\]'
PS1_BLACK_WHITE='\[\e[0;30m\]'
PS1_WHITE_BLACK='\[\e[97m\]'
PS1_CYAN_BLACK='\[\e[36m\]'
PS1_GREEN_BLACK='\[\e[32m\]'
export PS1="${PS1_CYAN_BLACK}${PS1_BOLD}\u${PS1_DIM}@${PS1_BOLD}\h ${PS1_RESET}${PS1_GREEN_BLACK}${PS1_BOLD}\w${PS1_RESET}$ ${PS1_RESET}"
export CLICOLOR=1
export LSCOLORS=ExFxBxDxCxegedabagacad
export force_color_prompt=yes

# Change HF caches
export HF_DATASETS_CACHE="/nlp/scr/dhei/.cache/huggingface/datasets"
export HUGGINGFACE_HUB_CACHE="/nlp/scr/dhei/.cache/huggingface/hub"
export HF_HOME="/nlp/scr/dhei/.cache/huggingface/hub"

# Change terminal formatting to UTF-8 for Python
export PYTHONIOENCODING=utf8

# Verify github
# I wish this could be run with .bashrc, but it slow
gitlogin() {
    ssh-keyscan -H github.com >> ~/.ssh/known_hosts
    ssh -T git@github.com
}

# # Welcome command!
# if [[ $- == *i* ]]; then
#     if command -v figlet &> /dev/null && command -v lolcat &> /dev/null; then
#         figlet "stanford" | lolcat
#     fi
#     if command -v nvidia-smi &> /dev/null && command -v lolcat &> /dev/null; then
#         nvidia-smi --query-gpu=name,utilization.gpu,memory.total,memory.free,memory.used --format=csv,noheader,nounits | \
#         awk -F, '{print "" $1 " | id ="$2", mem ="$3 " MB, free ="$4 " MB, used ="$5 " MB"}' | lolcat
#     fi
# fi

# devtools: binaries
export PATH="$HOME/.pixi/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"

# Copy ~/petri/.gitconfig -> ~/.gitconfig if not exist
[ -e ~/.gitconfig ] || cp ~/petri/.gitconfig ~/.gitconfig

#################
# slurm tooling #
#################
SLURM_TOOLS="$HOME/petri/slurm"

alias nlp="python3 $SLURM_TOOLS/summary.py"
alias nlpfast="python3 $SLURM_TOOLS/summary.py --fast"
alias nlpg="python3 $SLURM_TOOLS/summary.py --gpu-only"
alias nlpw="watch -n 10 -c python3 $SLURM_TOOLS/summary.py --gpu-only"

# per-pool views
alias sjag="python3 $SLURM_TOOLS/summary.py -p jag-urgent,jag-important,jag-hi,jag-standard,jag-lo"
alias smiso="python3 $SLURM_TOOLS/summary.py -p miso,miso-lo,miso-interactive"
alias ssphinx="python3 $SLURM_TOOLS/summary.py -p sphinx,sphinx-lo"
alias sjohn="python3 $SLURM_TOOLS/summary.py -p john,john-lo"
alias slo="python3 $SLURM_TOOLS/summary.py -p sc-loprio,sc-freegpu,sc-freecpu"

# priority queue
alias sp="python3 $SLURM_TOOLS/priority.py"
alias spa="python3 $SLURM_TOOLS/priority.py --all"

##################################
# slurm tooling (not ported yet) #
##################################
# # Defaults for the interactive helpers below. Override per-shell, e.g.
# #   SC_PART=miso-interactive SC_GPUS=2 sesh
# : "${SC_ACCOUNT:=nlp}"
# : "${SC_PART:=jag-standard}"
# : "${SC_GPUS:=1}"
# : "${SC_TIME:=8:00:00}"

# sesh() { # interactive shell on a compute node (dies with the session)
#     srun --account "$SC_ACCOUNT" --partition "$SC_PART" \
#          --gres "gpu:$SC_GPUS" --time "$SC_TIME" --pty "$SHELL"
# }
# gpus() { # reserve a devbox that outlives the shell; attach with `sa <jobid>`
#     salloc --account "$SC_ACCOUNT" --partition "$SC_PART" \
#            --gres "gpu:$SC_GPUS" --time "$SC_TIME"
# }
# devbox() { # long-lived cpu box named for `si` to find (7d on the preemptible pool)
#     sbatch --account "$SC_ACCOUNT" --partition sc-loprio \
#            --job-name "👋-$USER-interact-👋" --time 7-00:00:00 \
#            --wrap "sleep infinity"
# }
# sa() { # attach to a running job (--overlap gives you a second shell in it)
#     srun --jobid="$1" --mem=0 --overlap --pty "$SHELL"
# }
# si() { # attach to your "*interact*" job with the most GPUs
#     local jobid
#     jobid=$(python3 "$SLURM_TOOLS/interactive.py") || return $?
#     sa "$jobid"
# }
# sesha() { # attach to the first step of a job
#     sattach "$1.0"
# }
# sfollow() { # tail a job's stdout/stderr
#     local jobid=$1 stdout stderr
#     stdout=$(scontrol show job "$jobid" 2>/dev/null | awk -F= '/StdOut=/{print $2; exit}')
#     stderr=$(scontrol show job "$jobid" 2>/dev/null | awk -F= '/StdErr=/{print $2; exit}')
#     [ -z "$stdout" ] && { echo "no job $jobid"; return 1; }
#     tail -F "$stdout" ${stderr:+"$stderr"}
# }
