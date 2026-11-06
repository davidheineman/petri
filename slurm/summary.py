#!/usr/bin/env python3
"""Summary dashboard for every Slurm partition you can submit to on Stanford SC.

    python3 ~/petri/slurm/summary.py                 # all your partitions
    python3 ~/petri/slurm/summary.py -p jag-hi,miso  # just these
    python3 ~/petri/slurm/summary.py --fast          # queue table only (one squeue)
    python3 ~/petri/slurm/summary.py --one-line      # single status line
"""

import argparse
import string
import sys
from collections import defaultdict

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import common

MAX_WIDTH = 160
console = Console(width=min(Console().width, MAX_WIDTH))


# ── colour helpers ────────────────────────────────────────────────────────────


def gpu_color(pct):
    if pct < 60:
        return "green"
    if pct < 85:
        return "yellow"
    return "red"


def fair_color(score):
    if score >= 0.5:
        return "green"
    if score >= 0.2:
        return "yellow"
    return "red"


def spark_bar(pct, width=14):
    filled = round(width * pct / 100)
    return f"[dim]{'█' * filled}{'░' * (width - filled)}[/dim]"


# ── partitions ────────────────────────────────────────────────────────────────


def render_partitions(names, parts, usage, accounts, pnodes):
    """One row per partition, with a pool letter marking shared hardware."""
    pools = common.group_by_nodes(names, parts)
    pool_letter = {}
    multi = [nodes for nodes, members in pools.items() if len(members) > 1]
    for i, nodes in enumerate(sorted(multi, key=lambda n: -len(pools[n]))):
        for m in pools[nodes]:
            pool_letter[m] = string.ascii_uppercase[i % 26]

    rows, exposure = [], {}
    for name in names:
        info = parts[name]
        u = usage.get(name, {})
        total = u.get("total", 0)
        pct = u.get("pct", 0)
        color = gpu_color(pct) if total else "dim"
        # PreemptMode alone overstates the risk: it says what *would* happen,
        # not whether anything outranks you on these nodes. miso is
        # PreemptMode=REQUEUE but nothing on miso[1-5] beats its tier 1000.
        threats = common.preempted_by(name, parts, pnodes)
        mode = info.get("PreemptMode", "").lower()
        if mode in ("off", "", "none"):
            preempt_cell = "[dim green]never[/dim green]"
        elif not threats:
            preempt_cell = "[green]safe[/green]"
        else:
            preempt_cell = f"[red]{mode}[/red]"
            exposure[name] = threats
        if total:
            down = u.get("down", 0)
            tot = f"{u.get('up_total', total):,}"
            if down:
                tot += f" [red]-{down}[/red]"
            used, idle = (f"[{color}]{u['used']:,}[/{color}]",
                          f"[green]{u['idle']:,}[/green]")
            models = common.fmt_gpu_types(u.get("by_type_idle"), limit=4)
            bar_pct = pct
        else:
            bar_pct = (100 * u.get("cpu_alloc", 0) // u["cpu_total"]
                       if u.get("cpu_total") else 0)
            color = gpu_color(bar_pct)
            used = idle = tot = "[dim]—[/dim]"
            models = f"[dim]cpu only · {u.get('nodes', 0)} nodes[/dim]"
        rows.append({
            "Partition": f"[bold]{name}[/bold]",
            "Pool": pool_letter.get(name, ""),
            "pct": bar_pct, "color": color,
            "Used": used, "Idle": idle, "Total": tot,
            "Idle GPUs by model": models,
            "MaxWall": common.short_time(info.get("MaxTime")),
            "Tier": str(info.get("tier", 0)),
            "Preempt": preempt_cell,
            "Account": common.account_for_partition(info, accounts) or "any",
        })

    # Columns in drop order: the rightmost detail goes first when the terminal
    # is too narrow, so the table shrinks instead of being cropped.
    SPEC = [
        ("Partition", dict(min_width=14), 0),
        ("Pool", dict(justify="center", style="dim", min_width=4), 3),
        ("Utilisation", dict(min_width=12, no_wrap=True), 0),
        ("Used", dict(justify="right", min_width=5), 2),
        ("Idle", dict(justify="right", min_width=5), 0),
        ("Total", dict(justify="right", min_width=5), 2),
        ("Idle GPUs by model",
         dict(min_width=16, max_width=34, overflow="ellipsis", no_wrap=True), 4),
        ("MaxWall", dict(justify="right", min_width=7), 1),
        ("Tier", dict(justify="right", min_width=4), 0),
        ("Preempt", dict(min_width=7, no_wrap=True), 0),
        ("Account", dict(style="dim", min_width=7, no_wrap=True), 5),
    ]

    def build(drop_above, bar_width):
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
                  padding=(0, 1))
        keep = [(n, kw) for n, kw, prio in SPEC if prio <= drop_above]
        for n, kw in keep:
            t.add_column(n, **kw)
        for r in rows:
            cells = []
            for n, _ in keep:
                if n == "Utilisation":
                    cells.append(f"{spark_bar(r['pct'], bar_width)} "
                                 f"[{r['color']}]{r['pct']}%[/{r['color']}]")
                else:
                    cells.append(r[n])
            t.add_row(*cells)
        return t

    budget = console.width - 4  # panel border + padding
    for drop_above, bar_width in ((5, 14), (4, 14), (3, 12), (2, 10), (1, 8),
                                  (0, 6)):
        t = build(drop_above, bar_width)
        if console.measure(t).maximum <= budget or drop_above == 0:
            break

    children = [t]
    shared = [f"[dim]{pool_letter[members[0]]}[/dim] {', '.join(sorted(members))}"
              for nodes in sorted(multi, key=lambda n: -len(pools[n]))
              for members in [pools[nodes]]]
    if shared:
        children.append(Text.from_markup(
            "[dim]Pools are priority tiers over the same nodes, so their GPU "
            "counts are the same hardware:[/dim]\n  " + "\n  ".join(shared)
        ))
    if exposure:
        # 'safe'/'never' rows are omitted: nothing can evict them.
        lines = [f"[red]{n}[/red] ← {', '.join(t[:3])}"
                 + (f", +{len(t) - 3}" if len(t) > 3 else "")
                 for n, t in exposure.items()]
        children.append(Text.from_markup(
            "[dim]Preemption (PreemptType=preempt/partition_prio — only a "
            "strictly higher tier on the same nodes can evict you):[/dim]\n  "
            + "\n  ".join(lines)))
    return Panel(Group(*children),
                 title="[bold]Stanford SC · partitions you can submit to[/bold]",
                 border_style="cyan", expand=True)


# ── fairshare ─────────────────────────────────────────────────────────────────


def render_fairshare(fs, weights):
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
              padding=(0, 1))
    t.add_column("Account")
    t.add_column("FairShare", justify="right")
    t.add_column("Norm shares", justify="right", style="dim")
    t.add_column("Raw usage", justify="right", style="dim")

    for acct, v in sorted(fs.items(), key=lambda kv: -kv[1]["fairshare"]):
        c = fair_color(v["fairshare"])
        t.add_row(f"[bold]{acct}[/bold]",
                  f"[{c}]{v['fairshare']:.4f}[/{c}]",
                  f"{v['norm_shares']:.4f}",
                  f"{v['raw_usage']:,}")

    note = Text.from_markup(
        f"[dim]1.0 = full priority · usage decays with half-life "
        f"{weights.get('PriorityDecayHalfLife', '?')} · age caps at "
        f"{weights.get('PriorityMaxAge', '?')}[/dim]"
    )
    return Panel(Group(t, note), title="[bold]Your fairshare[/bold]",
                 border_style="cyan", expand=True)


def render_priority_formula(weights):
    def w(k):
        return int(weights.get(k, 0) or 0)

    terms = []
    for label, key in (("fairshare", "PriorityWeightFairShare"),
                       ("age", "PriorityWeightAge"),
                       ("partition tier", "PriorityWeightPartition"),
                       ("qos", "PriorityWeightQOS"),
                       ("jobsize", "PriorityWeightJobSize")):
        if w(key):
            terms.append(f"[cyan]{w(key):,}[/cyan]·{label}")
    tres = weights.get("PriorityWeightTRES", "")
    if tres:
        # Per-GPU-model weights: asking for an H200 buys more priority than a TitanXP.
        by_weight = defaultdict(list)
        for item in tres.split(","):
            if "=" not in item:
                continue
            name, val = item.split("=", 1)
            by_weight[val].append(name.replace("gres/gpu:", ""))
        best = max(by_weight, key=lambda v: int(v))
        terms.append(f"[cyan]≤{int(best):,}[/cyan]·gpu-model "
                     f"[dim]({', '.join(sorted(by_weight[best])[:4])} = {int(best):,})[/dim]")
    body = Text.from_markup("[bold]Job priority[/bold] = " + " + ".join(terms))
    return Panel(body, border_style="grey50", padding=(0, 1))


# ── queue ─────────────────────────────────────────────────────────────────────


def summarise_users(jobs, scope):
    users = defaultdict(lambda: {
        "run_jobs": 0, "pend_jobs": 0, "run_gpus": 0, "pend_gpus": 0,
        "run_nodes": 0, "runtimes": [], "pend_reasons": defaultdict(int),
        "gpu_types": defaultdict(int),
    })
    for j in jobs:
        if scope and not (set(j["partitions"]) & scope):
            continue
        v = users[j["user"]]
        if j["state"] == "RUNNING":
            v["run_jobs"] += 1
            v["run_gpus"] += j["gpus"]
            v["run_nodes"] += j["nodes"]
            v["runtimes"].append(j["runtime"])
            for t, n in j["gpu_types"].items():
                v["gpu_types"][t] += n
        else:
            v["pend_jobs"] += 1
            v["pend_gpus"] += j["gpus"]
            v["pend_reasons"][j["reason"] or "—"] += 1
    return dict(users)


def _runtime_seconds(s):
    """'1-00:46:16' / '16:20' -> seconds, for picking the longest job."""
    try:
        days, _, rest = s.partition("-")
        if not rest:
            rest, days = days, "0"
        bits = [int(x) for x in rest.split(":")]
        while len(bits) < 3:
            bits.insert(0, 0)
        h, m, sec = bits
        return ((int(days) * 24 + h) * 60 + m) * 60 + sec
    except (ValueError, AttributeError):
        return 0


def render_jobs(users, me, title, gpu_capacity, limit):
    ranked = sorted(users.items(), key=lambda kv: (-kv[1]["run_gpus"],
                                                   -kv[1]["pend_gpus"]))
    visible = ranked[:limit]
    if me in users and me not in {u for u, _ in visible}:
        visible.append((me, users[me]))

    rows = []
    for user, v in visible:
        is_me = user == me
        name = Text(user)
        if is_me:
            name.stylize("bold yellow")
            name.append(" ◀", style="yellow dim")
        longest = max(v["runtimes"], key=_runtime_seconds, default="—")
        reasons = ", ".join(
            f"{r}×{n}" if n > 1 else r
            for r, n in sorted(v["pend_reasons"].items(), key=lambda x: -x[1])
        ) or "—"
        c = "yellow" if is_me else "default"
        rows.append({
            "User": name,
            "Running": f"[{c}]{v['run_jobs']}[/{c}]",
            "R-GPUs": f"[{c}]{v['run_gpus']:,}[/{c}]",
            "GPU models": common.fmt_gpu_types(v["gpu_types"], limit=3),
            "Longest job": f"[dim]{longest}[/dim]",
            "Pending": str(v["pend_jobs"]) if v["pend_jobs"] else "[dim]—[/dim]",
            "P-GPUs": f"{v['pend_gpus']:,}" if v["pend_gpus"] else "[dim]—[/dim]",
            "Blocked by": reasons,
        })

    hidden = len(ranked) - len(visible)
    total_run = sum(v["run_gpus"] for v in users.values())
    total_pend = sum(v["pend_gpus"] for v in users.values())
    pct = 100 * total_run // gpu_capacity if gpu_capacity else 0
    color = gpu_color(pct)
    totals = {
        "User": "[bold]TOTAL[/bold]",
        "Running": f"[bold]{sum(v['run_jobs'] for v in users.values()):,}[/bold]",
        "R-GPUs": f"[{color} bold]{total_run:,}[/{color} bold]",
        "Pending": f"{sum(v['pend_jobs'] for v in users.values()):,}",
        "P-GPUs": f"{total_pend:,}",
    }

    # Keep the queue counts visible on small screens. Add details only when
    # the complete table fits inside the panel.
    specs = [
        ("User", dict(min_width=8, max_width=18, overflow="ellipsis",
                      no_wrap=True)),
        ("Running", dict(justify="right", min_width=7)),
        ("R-GPUs", dict(justify="right", min_width=6)),
        ("GPU models", dict(style="dim", min_width=14, overflow="ellipsis",
                            no_wrap=True)),
        ("Longest job", dict(justify="right", min_width=11)),
        ("Pending", dict(justify="right", min_width=7)),
        ("P-GPUs", dict(justify="right", min_width=6)),
        ("Blocked by", dict(style="dim", min_width=10, max_width=34,
                            overflow="ellipsis", no_wrap=True)),
    ]
    core = {"User", "Running", "R-GPUs", "Pending", "P-GPUs"}

    def build(extra, compact=False, blocked_width=34):
        t = Table(box=None if compact else box.SIMPLE, show_header=True,
                  header_style="bold dim", padding=(0, 0) if compact else (0, 1),
                  pad_edge=not compact)
        names = [n for n, kw in specs if n in core or n in extra]
        for n, kw in specs:
            if n in names:
                if compact:
                    compact_kw = dict(justify=kw.get("justify", "left"),
                                      overflow="ellipsis", no_wrap=True)
                    if n == "User":
                        compact_kw["max_width"] = min(10, max(6, console.width - 34))
                    elif n in ("GPU models", "Blocked by"):
                        compact_kw["max_width"] = 16
                    t.add_column((" " if n != "User" else "") + n,
                                 **compact_kw)
                else:
                    if n == "Blocked by":
                        kw = {**kw, "max_width": blocked_width}
                    t.add_column(n, **kw)
        for row in rows:
            t.add_row(*(f" {row[n]}" if compact and n != "User" else row[n]
                        for n in names))
        if hidden > 0:
            t.add_row(f"[dim]+{hidden} more[/dim]",
                      *(["[dim]…[/dim]"] * (len(names) - 1)))
        t.add_section()
        t.add_row(*(f" {totals.get(n, '')}" if compact and n != "User"
                    else totals.get(n, "") for n in names))
        return t

    budget = console.width - 4  # panel border + padding
    core_width = console.measure(build(())).maximum
    for extra in (("Blocked by", "GPU models", "Longest job"),
                  ("Blocked by", "GPU models"), ("Blocked by",), ()):
        for compact in (False, True):
            if compact and "Longest job" in extra:
                continue
            # Let long reasons use spare room in the regular layout.
            reserved = (16 if "GPU models" in extra else 0)
            reserved += 13 if "Longest job" in extra else 0
            blocked_width = min(34, max(10, budget - core_width - reserved - 2))
            candidate = build(extra, compact=compact,
                              blocked_width=blocked_width)
            if console.measure(candidate).maximum <= budget:
                t = candidate
                break
        else:
            continue
        break
    else:
        t = build((), compact=True)
    t.expand = True

    if gpu_capacity:
        status = f"{total_run:,} / {gpu_capacity:,} GPUs  ({pct}%)"
        bar_width = min(20, max(0, budget - len(status) - 4))
        subtitle = (f"{spark_bar(pct, bar_width)} " if bar_width else "")
        subtitle += f"[{color}]{status}[/{color}]"
    else:
        subtitle = f"[{color}]{total_run:,} GPUs running[/{color}]"
    return Panel(t, title=title, subtitle=subtitle, border_style="cyan",
                 expand=True)


# ── main ──────────────────────────────────────────────────────────────────────


def capacity(nodes, scope):
    """Schedulable GPUs reachable from the selected partitions, node counted once.

    Partitions overlap heavily here (sc-loprio alone spans the jagupard, miso
    and sphinx nodes), so dedupe by node name rather than by partition.

    Drained/down nodes are excluded: a drained node's GPUs can never be handed
    out, so folding them into the denominator makes the cluster look emptier
    than it is (miso reads 24/40 = 60% while miso2 is drained, when the real
    picture is 24/32 = 75%).
    """
    seen, total = set(), 0
    for n in nodes:
        if n["partition"] not in scope or n["node"] in seen or not n["up"]:
            continue
        seen.add(n["node"])
        total += sum(n["gpu_total"].values())
    return total


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-p", "--partition", default=None,
                        help="comma-separated partitions (default: all you can use)")
    parser.add_argument("-u", "--user", default=None, help="user to highlight")
    parser.add_argument("--limit", type=int, default=15,
                        help="max users listed in the queue table (default 15)")
    parser.add_argument("--fast", action="store_true",
                        help="queue table only; skips sinfo/sacctmgr/sshare")
    parser.add_argument("--one-line", action="store_true")
    parser.add_argument("--gpu-only", action="store_true",
                        help="hide cpu-only partitions")
    args = parser.parse_args()

    me = args.user or common.whoami()
    accounts = set(common.my_accounts(me))
    parts = common.all_partitions()

    if args.partition:
        names = [p.strip() for p in args.partition.split(",") if p.strip()]
        unknown = [n for n in names if n not in parts]
        if unknown:
            print(f"summary.py: unknown partition(s): {', '.join(unknown)}",
                  file=sys.stderr)
            return 2
    else:
        names = common.my_partitions(me, parts)
    if not names:
        console.print("[red]no partitions accessible to "
                      f"{me} (accounts: {', '.join(accounts) or 'none'})[/red]")
        return 1
    scope = set(names)

    if args.fast:
        with console.status("[dim]fetching queue...[/dim]"):
            jobs = common.fetch_jobs(names)
        users = summarise_users(jobs, scope)
        console.print()
        console.print(render_jobs(users, me, f"[bold]{len(names)} partitions[/bold]",
                                  0, args.limit))
        console.print()
        return 0

    with console.status("[dim]fetching...[/dim]"):
        nodes = common.fetch_nodes(names)
        usage = common.partition_usage(nodes)
        pnodes = common.partition_nodes()
        jobs = common.fetch_jobs(names)
        fs = common.fairshare(me)
        weights = common.priority_weights()

    if args.gpu_only:
        names = [n for n in names if usage.get(n, {}).get("total")]
        scope = set(names)

    users = summarise_users(jobs, scope)
    cap = capacity(nodes, scope)

    if args.one_line:
        run_gpus = sum(v["run_gpus"] for v in users.values())
        mine = users.get(me, {})
        pct = 100 * run_gpus // cap if cap else 0
        # Only the accounts that actually gate the selected partitions matter;
        # 'default' has a pristine fairshare but reaches no GPU partition.
        relevant = {common.account_for_partition(parts[n], accounts) for n in names}
        relevant.discard("")
        shown = sorted(relevant) or sorted(fs)
        fs_txt = "  ".join(
            f"{a} [{fair_color(fs[a]['fairshare'])}]{fs[a]['fairshare']:.3f}[/]"
            for a in shown if a in fs)
        console.print(
            f"[bold]SC[/bold] {len(names)}p  "
            f"GPUs [{gpu_color(pct)}]{run_gpus:,}/{cap:,} ({pct}%)[/]  "
            f"you [yellow]{mine.get('run_gpus', 0)}R/{mine.get('pend_gpus', 0)}P[/yellow]  "
            f"fairshare {fs_txt}"
        )
        return 0

    console.print()
    console.print(render_priority_formula(weights))
    console.print(render_partitions(names, parts, usage, accounts, pnodes))
    console.print(render_fairshare(fs, weights))
    console.print(render_jobs(
        users, me,
        f"[bold]Queue across your {len(names)} partitions[/bold]",
        cap, args.limit))
    console.print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
