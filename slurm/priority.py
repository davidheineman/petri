#!/usr/bin/env python3
"""Where you sit in the Slurm queue on Stanford SC.

Scheduling here is *tier-first*: Slurm drains the highest PriorityTier
partition before looking at the next one, so a pending job in ``jag-urgent``
(tier 2000) beats yours in ``jag-lo`` (tier 10) no matter how much priority you
have accrued. Since the jag-*/miso-*/sphinx-* tiers all sit on the same nodes,
"who is ahead of me" is computed per *node pool*, ordered by (tier, priority).

    python3 ~/petri/slurm/priority.py               # all partitions you can use
    python3 ~/petri/slurm/priority.py -p sc-loprio  # just one
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import common

console = Console()

PENDING_STATES = {"PENDING", "REQUEUE_HOLD", "CONFIGURING", "SUSPENDED"}

# Jobs parked for their own reasons aren't competing for the resources you
# want, so counting them as "ahead of you" badly overstates the queue. Matched
# as prefixes against squeue's Reason.
NOT_COMPETING = (
    "Dependency", "BeginTime", "JobHeldUser", "JobHeldAdmin", "JobArrayTaskLimit",
    "launch failed requeued held", "PartitionDown", "PartitionInactive",
    "ReqNodeNotAvail", "Reservation", "InvalidAccount", "InvalidQOS",
    "AssocGrpBillingMinutes", "NodeDown", "BadConstraints",
)


def competing(job):
    reason = job["reason"]
    return not any(reason.startswith(r) for r in NOT_COMPETING)


def tier_of(name, parts):
    return parts.get(name, {}).get("tier", 0)


def job_rank_key(job, parts):
    """How the scheduler orders work *within one node pool*: tier, then priority.

    Only meaningful between jobs contending for the same nodes — tiers are not
    comparable across pools (john's 1500 and miso's 1000 are different machines).
    """
    tier = max((tier_of(p, parts) for p in job["partitions"]), default=0)
    return (-tier, -job["priority"])


# ── tables ────────────────────────────────────────────────────────────────────


def _pending_table():
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
              padding=(0, 1), expand=True)
    t.add_column("Rank", justify="right", min_width=5)
    t.add_column("JobID", min_width=10)
    t.add_column("User", min_width=10)
    t.add_column("Account", style="dim", min_width=7)
    t.add_column("Partition", min_width=12, overflow="ellipsis", no_wrap=True)
    t.add_column("Tier", justify="right", min_width=4)
    t.add_column("GPUs", justify="right", min_width=4)
    t.add_column("Models", style="dim", min_width=10, overflow="ellipsis",
                 no_wrap=True)
    t.add_column("Walltime", justify="right", min_width=8)
    t.add_column("Priority", justify="right", min_width=8)
    t.add_column("Blocked by", style="dim", min_width=12, overflow="ellipsis",
                 no_wrap=True)
    return t


def _row(rank, j, parts, *, mine):
    style = "bold yellow" if mine else None

    def cell(s, dim=False):
        if style:
            return f"[{style}]{s}[/{style}]"
        return f"[dim]{s}[/dim]" if dim else str(s)

    tier = max((tier_of(p, parts) for p in j["partitions"]), default=0)
    return [
        cell(f"{rank:,}"),
        cell(j["jobid"]),
        cell(j["user"] + (" ◀" if mine else "")),
        cell(j["account"], dim=True),
        cell(",".join(j["partitions"])),
        cell(f"{tier:,}"),
        cell(j["gpus"] or "—", dim=not j["gpus"]),
        cell(common.fmt_gpu_types(j["gpu_types"], limit=2), dim=True),
        cell(common.short_time(j["timelimit"]), dim=True),
        cell(f"{j['priority']:,}"),
        cell(j["reason"] or "—", dim=True),
    ]


def render_top(pending, parts, me, top_n):
    t = _pending_table()
    for i, j in enumerate(pending[:top_n], 1):
        t.add_row(*_row(i, j, parts, mine=(j["user"] == me)))
    return Panel(t, title=f"[bold]Top {top_n} pending jobs by priority[/bold]",
                 border_style="cyan", expand=True)


def render_mine(pending, parts, me, limit):
    mine = [(i + 1, j) for i, j in enumerate(pending) if j["user"] == me]
    if not mine:
        return Panel(Text(f"No pending jobs for {me}.", style="dim"),
                     title=f"[bold]Your pending jobs ({me})[/bold]",
                     border_style="yellow", expand=True)

    total = len(pending)
    n = len(mine)
    t = _pending_table()
    show = mine if n <= limit else mine[: limit // 2] + [None] + mine[-(limit // 2):]
    for entry in show:
        if entry is None:
            t.add_row("[dim]…[/dim]", f"[dim]({n - limit} more)[/dim]",
                      *(["[dim]…[/dim]"] * 9))
            continue
        t.add_row(*_row(entry[0], entry[1], parts, mine=True))

    prios = [j["priority"] for _, j in mine]
    gpus = sum(j["gpus"] for _, j in mine)
    partitions = sorted({p for _, j in mine for p in j["partitions"]})
    prio_range = (f"{min(prios):,}" if min(prios) == max(prios)
                  else f"{min(prios):,}–{max(prios):,}")
    subtitle = (f"[yellow]{n}[/yellow] jobs  •  ranks "
                f"[yellow]{mine[0][0]:,}–{mine[-1][0]:,}[/yellow] of {total:,}  •  "
                f"{gpus:,} GPUs requested  •  priority {prio_range}  •  "
                f"{', '.join(partitions)}")
    return Panel(t, title=f"[bold yellow]Your pending jobs ({me})[/bold yellow]",
                 subtitle=subtitle, border_style="yellow", expand=True)


# ── "ahead of you", per node pool ─────────────────────────────────────────────


def render_ahead(pending, parts, names, me):
    """For each pool of machines you have a job queued on, who gets there first.

    A pool is the node set of one of your partitions. A job's tier *for that
    pool* comes from whichever of its partitions covers the whole pool, because
    partitions overlap without nesting: a job on ``jag-standard,sc-loprio``
    holds tier 1500 over the 16 jagupard nodes, but only sc-loprio's tier 5
    over the other 82 nodes sc-loprio reaches.
    """
    pnodes = common.partition_nodes()

    def tier_in(job, pool):
        tiers = [tier_of(p, parts) for p in job["partitions"]
                 if pool <= pnodes.get(p, set())]
        # Jobs that reach only part of the pool are left out: the nodes they
        # do contend for have their own (smaller) pool panel.
        return max(tiers) if tiers else None

    # One pool per distinct node set among your partitions.
    pools = {}
    for name in names:
        nodes = frozenset(pnodes.get(name, set()))
        if nodes:
            pools.setdefault(nodes, []).append(name)

    panels = []
    for pool, members in sorted(pools.items(), key=lambda kv: -len(kv[0])):
        label = "/".join(sorted(members))
        mine = [(tier_in(j, pool), j["priority"], j) for j in pending
                if j["user"] == me and tier_in(j, pool) is not None]
        if not mine:
            continue
        cutoff = max((t, p) for t, p, _ in mine)

        ahead = []
        for j in pending:
            if j["user"] == me:
                continue
            t = tier_in(j, pool)
            if t is not None and (t, j["priority"]) > cutoff:
                ahead.append((t, j))
        if not ahead:
            panels.append(Panel(
                Text(f"Nothing contending ahead of you on {label} "
                     f"({len(pool)} nodes).", style="green"),
                title=f"[bold]Ahead of you · {label}[/bold]",
                border_style="green", expand=True))
            continue

        agg = defaultdict(lambda: {"jobs": 0, "gpus": 0, "top_tier": 0,
                                   "top_prio": 0, "account": ""})
        for tier, j in ahead:
            a = agg[j["user"]]
            a["jobs"] += 1
            a["gpus"] += j["gpus"]
            if (tier, j["priority"]) > (a["top_tier"], a["top_prio"]):
                a["top_tier"], a["top_prio"] = tier, j["priority"]
            a["account"] = j["account"]

        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
                  padding=(0, 1), expand=True)
        t.add_column("User", min_width=12)
        t.add_column("Account", style="dim", min_width=8)
        t.add_column("Jobs ahead", justify="right", min_width=10)
        t.add_column("GPUs queued", justify="right", min_width=11)
        t.add_column("Top tier", justify="right", min_width=8)
        t.add_column("Top priority", justify="right", min_width=12)
        for user, a in sorted(agg.items(),
                              key=lambda kv: (-kv[1]["top_tier"], -kv[1]["top_prio"])):
            t.add_row(user, a["account"], f"{a['jobs']:,}", f"{a['gpus']:,}",
                      f"{a['top_tier']:,}", f"{a['top_prio']:,}")

        subtitle = (f"[red]{sum(a['jobs'] for a in agg.values()):,}[/red] jobs / "
                    f"[red]{sum(a['gpus'] for a in agg.values()):,}[/red] GPUs ahead of "
                    f"your best job [dim](tier {cutoff[0]:,}, priority {cutoff[1]:,})[/dim]")
        panels.append(Panel(t, title=f"[bold]Ahead of you · {label} "
                                     f"[dim]({len(pool)} nodes)[/dim][/bold]",
                            subtitle=subtitle, border_style="red", expand=True))
    return panels


# ── running jobs ──────────────────────────────────────────────────────────────


def _parse_end(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return datetime.max


def render_running(running, scope, limit):
    jobs = [j for j in running if set(j["partitions"]) & scope and j["gpus"]]
    if not jobs:
        return Panel(Text("No GPU jobs running on your partitions.", style="dim"),
                     title="[bold]Running on your partitions[/bold]",
                     border_style="cyan", expand=True)

    jobs.sort(key=lambda j: _parse_end(j["endtime"]))
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
              padding=(0, 1), expand=True)
    t.add_column("JobID", min_width=10)
    t.add_column("User", min_width=10)
    t.add_column("Account", style="dim", min_width=7)
    t.add_column("Partition", min_width=10, overflow="ellipsis", no_wrap=True)
    t.add_column("GPUs", justify="right", min_width=4)
    t.add_column("Models", style="dim", min_width=10, overflow="ellipsis",
                 no_wrap=True)
    t.add_column("Time left", justify="right", min_width=10)
    t.add_column("Ends at", style="dim", min_width=19)
    t.add_column("GPUs freed", justify="right", min_width=10)

    cum = 0
    for j in jobs[:limit]:
        cum += j["gpus"]
        t.add_row(j["jobid"], j["user"], j["account"], j["partition"],
                  f"{j['gpus']}", common.fmt_gpu_types(j["gpu_types"], limit=2),
                  j["timeleft"], j["endtime"], f"{cum:,}")
    extra = len(jobs) - limit
    if extra > 0:
        t.add_row("[dim]…[/dim]", f"[dim]+{extra} more[/dim]", *(["[dim]…[/dim]"] * 7))

    subtitle = (f"[cyan]{len(jobs):,}[/cyan] running GPU jobs  •  "
                f"[cyan]{sum(j['gpus'] for j in jobs):,}[/cyan] GPUs in use")
    return Panel(t, title="[bold]Running on your partitions (soonest to finish)[/bold]",
                 subtitle=subtitle, border_style="cyan", expand=True)


# ── cluster usage ─────────────────────────────────────────────────────────────


def _usage_table(title, label, agg, me_key, top_n):
    items = sorted(agg.items(), key=lambda kv: -kv[1]["gpus"])
    total_gpus = sum(v["gpus"] for v in agg.values())
    total_jobs = sum(v["jobs"] for v in agg.values())

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
              padding=(0, 1), expand=True)
    t.add_column(label, overflow="ellipsis", no_wrap=True, ratio=3)
    t.add_column("GPUs", justify="right", ratio=1)
    t.add_column("%", justify="right", style="dim", ratio=1)

    visible = items[:top_n]
    if me_key and me_key in agg and me_key not in {k for k, _ in visible}:
        visible.append((me_key, agg[me_key]))
    for key, v in visible:
        is_me = key == me_key
        pct = 100.0 * v["gpus"] / total_gpus if total_gpus else 0.0
        cells = [f"{key}{' ◀' if is_me else ''}", f"{v['gpus']:,}", f"{pct:.1f}%"]
        if is_me:
            cells = [f"[bold yellow]{c}[/bold yellow]" for c in cells]
        t.add_row(*cells)

    hidden = max(0, len(items) - top_n)
    if hidden:
        hidden_gpus = sum(v["gpus"] for _, v in items[top_n:])
        t.add_row(f"[dim]+{hidden} more[/dim]", f"[dim]{hidden_gpus:,}[/dim]",
                  f"[dim]{100.0 * hidden_gpus / total_gpus:.1f}%[/dim]"
                  if total_gpus else "")

    return Panel(t, title=f"[bold]{title}[/bold]",
                 subtitle=f"[cyan]{total_gpus:,}[/cyan] GPUs · "
                          f"[cyan]{total_jobs:,}[/cyan] jobs",
                 border_style="cyan", expand=True)


def render_usage(running, scope, me, top_n):
    by_account = defaultdict(lambda: {"gpus": 0, "jobs": 0})
    by_partition = defaultdict(lambda: {"gpus": 0, "jobs": 0})
    by_user = defaultdict(lambda: {"gpus": 0, "jobs": 0})
    my_account = None

    for j in running:
        if not j["gpus"] or not (set(j["partitions"]) & scope):
            continue
        for key, agg in ((j["account"], by_account),
                         (j["partition"], by_partition),
                         (j["user"], by_user)):
            agg[key]["gpus"] += j["gpus"]
            agg[key]["jobs"] += 1
        if j["user"] == me:
            my_account = my_account or j["account"]

    return [
        _usage_table("Usage by account", "Account", by_account, my_account, top_n),
        _usage_table("Usage by partition", "Partition", by_partition, None, top_n),
        _usage_table("Usage by user", "User", by_user, me, top_n),
    ]


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-p", "--partition", default=None,
                        help="comma-separated partitions (default: all you can use)")
    parser.add_argument("-n", "--top", type=int, default=25,
                        help="pending jobs to list (default 25)")
    parser.add_argument("--mine-limit", type=int, default=20,
                        help="max rows for your own jobs (default 20)")
    parser.add_argument("--running-limit", type=int, default=15,
                        help="max running jobs to list (default 15)")
    parser.add_argument("--usage-top", type=int, default=8,
                        help="rows per usage table (default 8)")
    parser.add_argument("-u", "--user", default=None,
                        help="user to highlight (default: $USER)")
    parser.add_argument("-a", "--all", action="store_true",
                        help="also count jobs parked on dependencies/holds, "
                             "which are not actually competing for resources")
    args = parser.parse_args()

    me = args.user or common.whoami()
    parts = common.all_partitions()
    if args.partition:
        names = [p.strip() for p in args.partition.split(",") if p.strip()]
        unknown = [n for n in names if n not in parts]
        if unknown:
            print(f"priority.py: unknown partition(s): {', '.join(unknown)}",
                  file=sys.stderr)
            return 2
    else:
        names = common.my_partitions(me, parts)
    if not names:
        console.print(f"[red]no partitions accessible to {me}[/red]")
        return 1
    scope = set(names)

    with console.status("[dim]fetching queue...[/dim]"):
        jobs = common.fetch_jobs(names)
    pending = [j for j in jobs if j["state"] in PENDING_STATES]
    parked = [j for j in pending if not competing(j)]
    if not args.all:
        pending = [j for j in pending if competing(j)]
    # Across pools only raw priority is comparable, so the overview table is
    # ordered by priority; the per-pool panels below apply tier-first ordering.
    pending.sort(key=lambda j: -j["priority"])
    running = [j for j in jobs if j["state"] == "RUNNING"]

    console.print()
    grid = Table.grid(expand=True, padding=(0, 1))
    panels = render_usage(running, scope, me, args.usage_top)
    for _ in panels:
        grid.add_column(ratio=1)
    grid.add_row(*panels)
    console.print(grid)
    if parked and not args.all:
        console.print(f"[dim]hiding {len(parked):,} pending jobs parked on "
                      f"dependencies/holds (-a to include)[/dim]")
    if not pending:
        console.print("[dim]nothing contending on your partitions.[/dim]\n")
    else:
        console.print(render_top(pending, parts, me, args.top))
        console.print(render_mine(pending, parts, me, args.mine_limit))
        for p in render_ahead(pending, parts, names, me):
            console.print(p)
    console.print(render_running(running, scope, args.running_limit))
    console.print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
