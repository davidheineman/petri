#!/usr/bin/env python3
"""Shared Slurm helpers for Stanford SC.

Stanford SC is organised very differently from FAIR SC, which is what the
original versions of these scripts targeted:

  * Access is gated by **partition** (via the partition's ``AllowAccounts``),
    not by QoS. Nearly every job here runs under QoS ``normal``; the partition
    carries the QoS, the priority tier and the preemption policy.
  * Partitions overlap. ``jag-urgent``/``jag-important``/``jag-hi``/
    ``jag-standard``/``jag-lo`` are five priority tiers over the *same* 16
    jagupard nodes, and ``sc-loprio`` floats over most of the cluster as a
    preemptible pool.
  * GPUs are heterogeneous (~30 models, 1-8 per node), so "nodes x 8" is
    meaningless. Everything below counts GPUs from the TRES strings.
"""

import os
import re
import subprocess
from collections import defaultdict

# gres/gpu:a100=8 (TRES strings) and gpu:a100:8 / gpu:a100:8(IDX:0-7) (gres strings)
_TRES_GPU_TYPED = re.compile(r"gres/gpu:([^=,]+)=(\d+)")
_TRES_GPU_TOTAL = re.compile(r"gres/gpu=(\d+)")
_GRES_GPU_TYPED = re.compile(r"gpu:([^:(,\s]+):(\d+)")
_GRES_GPU_PLAIN = re.compile(r"gpu:(\d+)(?=\D|$)")

# Node state suffixes: * not responding, ~ powered down, # powering up,
# % powering down, $ reserved, @ pending reboot, - planned by backfill.
_STATE_SUFFIXES = "*~#%$@-+"
UNAVAILABLE_STATES = {
    "down", "drain", "drng", "draining", "drained", "fail", "failg", "failing",
    "maint", "unk", "unknown", "boot", "pow_dn", "powering_down", "inval",
}


def run(cmd):
    """Run a shell command, return stripped stdout ('' on failure)."""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    except OSError:
        return ""
    return p.stdout.strip()


def whoami():
    return os.environ.get("USER") or os.environ.get("LOGNAME") or run("whoami")


# ── TRES parsing ──────────────────────────────────────────────────────────────


def parse_tres(s):
    """'cpu=16,mem=128G,gres/gpu=8' -> {'cpu': '16', 'mem': '128G', ...}."""
    out = {}
    for item in (s or "").split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def tres_gpus(tres, nodes=1):
    """Total GPUs described by a TRES string.

    squeue's ``tres-alloc`` is job-total for both running and pending jobs
    (verified: a 3-node job requesting 1 GPU/node reports ``gres/gpu=3``), so
    ``nodes`` is only used for the ``tres-per-node`` fallback.
    """
    if not tres or tres in ("N/A", "(null)"):
        return 0
    m = _TRES_GPU_TOTAL.search(tres)
    if m:
        return int(m.group(1))
    typed = sum(int(n) for _, n in _TRES_GPU_TYPED.findall(tres))
    if typed:
        return typed
    # tres-per-node style: 'gres/gpu:h200:1' or 'gres/gpu:4'
    per_node = sum(int(n) for _, n in _GRES_GPU_TYPED.findall(tres))
    if not per_node:
        per_node = sum(int(n) for n in _GRES_GPU_PLAIN.findall(tres))
    return per_node * max(nodes, 1)


def tres_gpu_types(tres):
    """{'a100': 8} from a TRES or gres string. Untyped requests land under 'any'."""
    out = defaultdict(int)
    for name, n in _TRES_GPU_TYPED.findall(tres or ""):
        out[name] += int(n)
    if out:
        return dict(out)
    for name, n in _GRES_GPU_TYPED.findall(tres or ""):
        out[name] += int(n)
    if out:
        return dict(out)
    total = _TRES_GPU_TOTAL.search(tres or "")
    if total and int(total.group(1)):
        out["any"] = int(total.group(1))
    return dict(out)


def short_time(t):
    """'21-00:00:00' -> '21d', '3-12:00:00' -> '3d12h', '12:00:00' -> '12h'."""
    if not t or t in ("UNLIMITED", "NONE", "N/A", "Unknown"):
        return t or "—"
    if "-" in t:
        days, rest = t.split("-", 1)
        hours = rest.split(":")[0]
        return f"{days}d" if hours in ("00", "0") else f"{days}d{int(hours)}h"
    parts = t.split(":")
    if len(parts) == 3:
        h, m, _ = parts
        return f"{int(h)}h" if int(h) else f"{int(m)}m"
    return t


def fmt_gpu_types(types, limit=3):
    """{'a100': 8, 'a40': 2} -> 'a100:8, a40:2'."""
    if not types:
        return "—"
    items = sorted(types.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ", ".join(f"{k}:{v}" for k, v in items[:limit])
    if len(items) > limit:
        shown += f", +{len(items) - limit}"
    return shown


# ── who am I ──────────────────────────────────────────────────────────────────


def my_accounts(user=None):
    """Slurm accounts the user is associated with, e.g. ['default','miso','nlp']."""
    user = user or whoami()
    out = run(f"sacctmgr -nP show assoc user={user} format=Account")
    accts = {line.strip() for line in out.splitlines() if line.strip()}
    return sorted(accts)


def my_unix_groups(user=None):
    user = user or whoami()
    out = run(f"id -Gn {user}")
    return set(out.split())


# ── partitions ────────────────────────────────────────────────────────────────

_PART_KEYS = (
    "AllowGroups", "AllowAccounts", "AllowQos", "DenyAccounts", "DenyQos",
    "QoS", "DefaultTime", "MaxTime", "Nodes", "TotalNodes", "TotalCPUs",
    "PriorityJobFactor", "PriorityTier", "PreemptMode", "TRES", "State",
    "Default", "GraceTime",
)


def all_partitions():
    """{name: {field: value}} for every partition, from `scontrol show partition`."""
    raw = run("scontrol show partition")
    parts = {}
    for chunk in raw.split("PartitionName="):
        chunk = chunk.strip()
        if not chunk:
            continue
        name = chunk.split(None, 1)[0]
        info = {"name": name}
        for key in _PART_KEYS:
            m = re.search(rf"\b{key}=(\S*)", chunk)
            info[key] = m.group(1) if m else ""
        info["tres"] = parse_tres(info.get("TRES", ""))
        info["gpu_types"] = tres_gpu_types(info.get("TRES", ""))
        info["gpus"] = tres_gpus(info.get("TRES", ""))
        try:
            info["tier"] = int(info.get("PriorityTier") or 0)
        except ValueError:
            info["tier"] = 0
        parts[name] = info
    return parts


def _allowed(value, mine):
    """AllowX matching: 'ALL' or a comma list intersecting `mine`."""
    if not value or value in ("ALL", "(null)"):
        return True
    return bool(mine & {v.strip() for v in value.split(",")})


def my_partitions(user=None, partitions=None):
    """Partitions the user may actually submit to, ordered by priority tier.

    Access is AllowAccounts (intersected with the user's Slurm accounts) AND
    AllowGroups (intersected with their unix groups), minus DenyAccounts.
    """
    accounts = set(my_accounts(user))
    groups = my_unix_groups(user)
    parts = partitions if partitions is not None else all_partitions()

    mine = []
    for name, info in parts.items():
        if not _allowed(info.get("AllowAccounts"), accounts):
            continue
        if not _allowed(info.get("AllowGroups"), groups):
            continue
        deny = info.get("DenyAccounts")
        if deny and deny not in ("(null)", "") and accounts & {
            d.strip() for d in deny.split(",")
        }:
            continue
        mine.append(name)
    mine.sort(key=lambda n: (-parts[n]["tier"], n))
    return mine


def account_for_partition(info, user_accounts):
    """The account you'd submit under for this partition ('' if any works)."""
    allow = info.get("AllowAccounts")
    if not allow or allow in ("ALL", "(null)"):
        return ""
    usable = [a for a in allow.split(",") if a.strip() in user_accounts]
    return usable[0].strip() if usable else ""


def preempted_by(name, parts, pnodes):
    """Partitions that can actually preempt jobs in `name`, highest tier first.

    PreemptType is preempt/partition_prio here, so a job is only preempted by a
    job from a partition with a *strictly higher* PriorityTier that shares its
    nodes. A partition's own PreemptMode=REQUEUE says what would happen to it,
    not whether it can happen: nothing on the miso nodes outranks miso's tier
    1000, so a miso job runs its full walltime untouched.
    """
    info = parts.get(name, {})
    if (info.get("PreemptMode", "").lower() or "off") in ("off", "none"):
        return []
    tier = info.get("tier", 0)
    nodes = pnodes.get(name, set())
    threats = [q for q, qn in pnodes.items()
               if q != name and qn & nodes and parts.get(q, {}).get("tier", 0) > tier]
    return sorted(threats, key=lambda q: (-parts[q]["tier"], q))


def partition_nodes(partitions=None):
    """{partition: {node, ...}} — one cheap sinfo call.

    Needed because partitions overlap rather than nest: sc-loprio spans most of
    the cluster including the jagupard/miso/sphinx nodes, so "who is competing
    with me for these machines" has to be answered by node set, not by name.
    """
    cmd = "sinfo -h -N -O 'NodeList:40,Partition:40'"
    if partitions:
        cmd += f" --partition={','.join(partitions)}"
    out = defaultdict(set)
    for line in run(cmd).splitlines():
        f = line.split()
        if len(f) >= 2:
            out[f[1].rstrip("*")].add(f[0])
    return dict(out)


def group_by_nodes(names, parts):
    """Group partition names that cover the identical node set.

    On SC the jag-* tiers (and miso/miso-lo, sphinx/sphinx-lo, ...) are the same
    hardware at different priorities, so summing their GPUs would triple-count.
    """
    groups = defaultdict(list)
    for n in names:
        groups[parts[n].get("Nodes", "")].append(n)
    return groups


# ── nodes ─────────────────────────────────────────────────────────────────────


def fetch_nodes(partitions=None):
    """Per-node rows (one per node *per partition* it belongs to)."""
    cmd = (
        "sinfo -h -N -O "
        "'NodeList:40,Partition:40,Gres:120,GresUsed:160,StateCompact:20,"
        "CPUsState:40,Memory:20,FreeMem:20'"
    )
    if partitions:
        cmd += f" --partition={','.join(partitions)}"
    rows = []
    for line in run(cmd).splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        node, part, gres, gres_used, state = f[0], f[1], f[2], f[3], f[4]
        cpus_state = f[5] if len(f) > 5 else ""
        base = state.rstrip(_STATE_SUFFIXES)
        total = tres_gpu_types(gres)
        used = tres_gpu_types(gres_used)
        # allocated/idle/other/total, e.g. '30/10/0/40'
        cpu_alloc = cpu_total = 0
        if cpus_state.count("/") == 3:
            try:
                a, _i, _o, t = cpus_state.split("/")
                cpu_alloc, cpu_total = int(a), int(t)
            except ValueError:
                pass
        rows.append({
            "node": node,
            "partition": part.rstrip("*"),
            "state": state,
            "base_state": base,
            "up": base not in UNAVAILABLE_STATES,
            "gpu_total": total,
            "gpu_used": used,
            "cpu_alloc": cpu_alloc,
            "cpu_total": cpu_total,
        })
    return rows


def partition_usage(nodes):
    """Aggregate node rows into per-partition GPU/CPU utilisation."""
    agg = defaultdict(lambda: {
        "used": 0, "idle": 0, "total": 0, "down": 0,
        "by_type_total": defaultdict(int), "by_type_idle": defaultdict(int),
        "nodes": 0, "nodes_down": 0, "cpu_alloc": 0, "cpu_total": 0,
    })
    for n in nodes:
        a = agg[n["partition"]]
        a["nodes"] += 1
        total = sum(n["gpu_total"].values())
        used = sum(n["gpu_used"].values())
        a["total"] += total
        for t, c in n["gpu_total"].items():
            a["by_type_total"][t] += c
        if not n["up"]:
            a["down"] += total
            a["nodes_down"] += 1
            continue
        a["used"] += used
        a["idle"] += max(total - used, 0)
        a["cpu_alloc"] += n["cpu_alloc"]
        a["cpu_total"] += n["cpu_total"]
        for t, c in n["gpu_total"].items():
            free = c - n["gpu_used"].get(t, 0)
            if free > 0:
                a["by_type_idle"][t] += free
    for a in agg.values():
        a["by_type_total"] = dict(a["by_type_total"])
        a["by_type_idle"] = dict(a["by_type_idle"])
        a["pct"] = 100 * a["used"] // a["total"] if a["total"] else 0
    return dict(agg)


# ── jobs ──────────────────────────────────────────────────────────────────────

# squeue's %-format has no tres-alloc specifier, and its -O JobID prints the
# *array* job id rather than the task id, so use -O with JobArrayID and a
# zero-width '|' suffix as the field delimiter. One call gets everything.
_JOB_FIELDS = (
    "JobArrayID", "PriorityLong", "Partition", "UserName", "Account", "QOS",
    "State", "NumNodes", "tres-alloc", "tres-per-node", "TimeUsed",
    "TimeLimit", "TimeLeft", "EndTime", "Reason", "Name",
)
_JOB_FMT = ",".join(f"{f}:.0|" for f in _JOB_FIELDS)


def fetch_jobs(partitions=None, states=None, user=None):
    """All matching jobs as dicts, with GPU counts resolved from TRES."""
    cmd = f"squeue -h -O '{_JOB_FMT}'"
    if partitions:
        cmd += f" --partition={','.join(partitions)}"
    if states:
        cmd += f" --states={','.join(states)}"
    if user:
        cmd += f" -u {user}"

    jobs = []
    for line in run(cmd).splitlines():
        f = line.split("|")
        if len(f) < len(_JOB_FIELDS):
            continue
        (jobid, prio, part, user_, acct, qos, state, nodes, tres, per_node,
         runtime, timelimit, timeleft, endtime, reason, name) = f[:16]
        try:
            nodes_i = int(nodes)
        except ValueError:
            nodes_i = 1
        try:
            prio_i = int(prio)
        except ValueError:
            prio_i = 0
        gpus = tres_gpus(tres, nodes_i) or tres_gpus(per_node, nodes_i)
        types = tres_gpu_types(tres) or tres_gpu_types(per_node)
        # A pending job can name several partitions ('iliad,iliad-lo,sc-loprio');
        # it competes in each, so keep the full list and use the first as primary.
        part_list = [x.rstrip("*") for x in part.strip().split(",") if x]
        jobs.append({
            "jobid": jobid.strip(), "priority": prio_i,
            "partition": part_list[0] if part_list else "",
            "partitions": part_list, "user": user_.strip(),
            "account": acct.strip(), "qos": qos.strip(),
            "state": state.strip(), "nodes": nodes_i, "gpus": gpus,
            "gpu_types": types, "runtime": runtime.strip(),
            "timelimit": timelimit.strip(), "timeleft": timeleft.strip(),
            "endtime": endtime.strip(),
            "reason": reason.strip().strip("()"), "name": name.strip(),
        })
    return jobs


# ── fairshare / config ────────────────────────────────────────────────────────


def fairshare(user=None):
    """{account: {...}} fairshare for the user's own associations."""
    user = user or whoami()
    out = run(
        f"sshare -nP -U -u {user} -o "
        "Account,User,RawShares,NormShares,RawUsage,EffectvUsage,FairShare,LevelFS"
    )
    res = {}
    for line in out.splitlines():
        f = [x.strip() for x in line.split("|")]
        if len(f) < 8 or not f[0]:
            continue
        def num(x, cast=float):
            try:
                return cast(x)
            except (TypeError, ValueError):
                return 0.0
        res[f[0]] = {
            "account": f[0], "raw_shares": f[2], "norm_shares": num(f[3]),
            "raw_usage": num(f[4], int), "eff_usage": num(f[5]),
            "fairshare": num(f[6]), "levelfs": f[7],
        }
    return res


def priority_weights():
    """PriorityWeight* from `scontrol show config`, plus the decay half-life."""
    out = run("scontrol show config")
    cfg = {}
    for line in out.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("PriorityWeight") or k in (
            "PriorityDecayHalfLife", "PriorityMaxAge", "PriorityType",
            "PriorityFlags",
        ):
            cfg[k] = v
    return cfg
