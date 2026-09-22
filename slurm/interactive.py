#!/usr/bin/env python3
"""Pick a running 'interactive' Slurm job of yours and print its jobid.

Filters squeue to your RUNNING jobs whose name contains 'interact' (the
sbatch in the README names them '👋-$USER-interact-👋'), then picks the one
allocating the most GPUs. Prints just the jobid to stdout so it can be fed to
`sa`:

    sa "$(python3 ~/petri/slurm/interactive.py)"
"""

import argparse
import sys

import common


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--match", default="interact",
                        help="substring the job name must contain (default: interact)")
    parser.add_argument("-u", "--user", default=None)
    args = parser.parse_args()

    user = args.user or common.whoami()
    if not user:
        print("interactive.py: cannot determine user", file=sys.stderr)
        return 2

    jobs = common.fetch_jobs(user=user, states=["RUNNING"])
    needle = args.match.lower()
    candidates = [j for j in jobs if needle in j["name"].lower()]
    if not candidates:
        print(f"interactive.py: no RUNNING job of {user}'s matching "
              f"'{args.match}'", file=sys.stderr)
        return 1

    # Most GPUs first, then the most recently submitted (highest jobid).
    def key(j):
        head = j["jobid"].split("_")[0]
        return (j["gpus"], int(head) if head.isdigit() else 0)

    best = max(candidates, key=key)
    print(f"interactive.py: attaching to {best['jobid']} ({best['name']}, "
          f"{best['gpus']} GPU, {best['partition']} on "
          f"{best['nodes']} node{'s' if best['nodes'] != 1 else ''})",
          file=sys.stderr)
    print(best["jobid"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
