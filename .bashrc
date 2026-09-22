# # interactive session (exits when session is done)
# alias sesh='\
# srun --account transformer2 \
#      --qos h200_transformer2_high \
#      --exclusive \
#      --mem 0 \
#      --gpus-per-node 8 \
#      --time 10:00:00 \
#      --pty \
#      $SHELL
# ' # h200_transformer2_high, h200_dev (h200_dev has a 1 day, 16 GPU max; h200_transformer2_high has no max. Both are top priority)
# sesha() { # attach to interactive session
#     sattach $*.0
# }

# # reserve gpus (devbox) -> srun --pty bash
# alias gpus='\
# salloc \
#   --account transformer2 \
#   --qos h200_dev \
#   --exclusive \
#   --mem 0 \
#   --gpus-per-node 8 \
#   --time 10:00:00
# '
# sa() { # <- attach to devbox (--overlap will make a new sesh)
#      srun --jobid=$* --mem=0 --overlap --pty $SHELL
# }

# si() { # <- attach to the running "interact*" job with the most GPUs
#     local jobid
#     jobid=$(python ~/fairdev/slurm/interactive.py) || return $?
#     sa "$jobid"
# }

alias cpus='srun --partition=transformer2 --gres=gpu:0 --cpus-per-task=4 --qos h200_dev --pty bash'

# (%.XXj controls name size)
alias sq='squeue --user dhei --format="%.18i %.12P %.20j %.8u %.8T %.10M %.6D %R"'
alias sc='scancel'
alias scall='scancel -u dhei'
alias saccts='sacctmgr show qos format=name%30,GrpTRES%50,priority' # check all accounts on the cluster

alias sqw='watch -n 1 squeue -u dhei'

# check usage in our accounts
alias susage='squeue --Format=JobID,UserName,Account,QOS,NumNodes,tres-per-job:.30,tres-per-node:.50,Reason:.30 --qos h200_agentic-models_high,h200_compact-models_high'

# show stats
alias ss='sstat -j' # <job-id>

# sfollow() { # (works with fair-tbd train jobs; anything else?)
#   local jobid=$1
#   local stdout
#   stdout=$(scontrol show job "$jobid" 2>/dev/null | awk -F= '/StdOut=/{print $2; exit}')
#   [ -z "$stdout" ] && { echo "no job $jobid"; return 1; }
#   local dir=$(dirname "$stdout")
#   # prefer per-rank rank-0 files if they exist (xlformers/stool layout), else fall back to StdOut/StdErr
#   local rank0=( "$dir/${jobid}_0".{out,err} )
#   if [ -f "${rank0[0]}" ]; then
#     tail -F "${rank0[@]}"
#   else
#     tail -F "$dir/${jobid}".{stdout,stderr}
#   fi
# }

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
pip_path=$(which pip)
[ -n "$pip_path" ] && sudo mv "$pip_path" "$(dirname "$pip_path")/pipforce"
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

# # Show cluster usage
# alias tt="python ~/fairdev/slurm/summary.py --qos h200_transformer2_high --fast" # tt stands for "transformer2"
# alias ttt="python ~/fairdev/slurm/summary.py --qos h200_transformer2_high" # tt stands for "transformer2"
# alias comm="python ~/fairdev/slurm/summary.py --qos h200_comm_shared" # comm stands for "h200_comm_shared"
# alias lowest="python ~/fairdev/slurm/summary.py --qos h200_lowest" # lowest stands for "h200_lowest"
# alias ttall="python ~/fairdev/slurm/summary.py" # all QoSes
# alias ttw="watch -n 10 python ~/fairdev/slurm/summary.py"

# alias sp="python ~/fairdev/slurm/priority.py" # "slurm priority"

# alias store="python ~/fairdev/storage/monitor.py" # disk usage

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

# Copy ~/petri/.gitconfig -> ~/.gitconfig if not exist
[ -e ~/.gitconfig ] || cp ~/petri/.gitconfig ~/.gitconfig