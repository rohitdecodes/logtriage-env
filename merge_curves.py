"""
merge_curves.py — Merge checkpoint data from all 3 tasks into one reward_curve.png
Place in repo root. Run after all 3 tasks have completed training.

Usage:
    python merge_curves.py

Output:
    reward_curve.png — 3-line plot, one per task
"""

import json
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

CHECKPOINT_DIR = "./phase2_checkpoints"
OUTPUT_PATH = "reward_curve.png"

TASKS = {
    "single_crash": {
        "color": "#00ff9d",
        "label": "Task 1: Single Crash (Easy)",
        "max_steps": 8,
    },
    "cascading_failure": {
        "color": "#ffaa00",
        "label": "Task 2: Cascading Failure (Medium)",
        "max_steps": 12,
    },
    "silent_degradation": {
        "color": "#ff3b3b",
        "label": "Task 3: Silent Degradation (Hard)",
        "max_steps": 15,
    },
}


def load_task_rewards(task_id):
    """Load rewards from highest-episode checkpoint for a given task."""
    if not os.path.isdir(CHECKPOINT_DIR):
        print(f"[ERROR] Checkpoint dir not found: {CHECKPOINT_DIR}")
        return []

    files = [
        f for f in os.listdir(CHECKPOINT_DIR)
        if f.startswith(task_id) and f.endswith(".json")
    ]

    if not files:
        print(f"[WARN] No checkpoint found for task: {task_id}")
        return []

    # Pick checkpoint with highest episode number
    def ep_num(fname):
        try:
            return int(fname.split("_ep")[1].replace(".json", ""))
        except Exception:
            return 0

    latest = sorted(files, key=ep_num)[-1]
    path = os.path.join(CHECKPOINT_DIR, latest)

    with open(path) as f:
        data = json.load(f)

    rewards = data.get("rewards", [])
    print(f"[OK] {task_id}: loaded {len(rewards)} episodes from {latest}")
    return rewards


def smooth(rewards, window=5):
    """Rolling average smoothing."""
    smoothed = []
    for i in range(len(rewards)):
        w = rewards[max(0, i - window + 1):i + 1]
        smoothed.append(sum(w) / len(w))
    return smoothed


def print_stats(task_id, rewards):
    """Print first/last 10 episode averages."""
    if not rewards:
        return
    first10 = rewards[:min(10, len(rewards))]
    last10 = rewards[-min(10, len(rewards)):]
    avg_first = sum(first10) / len(first10)
    avg_last = sum(last10) / len(last10)
    improvement = avg_last - avg_first
    sign = "+" if improvement >= 0 else ""
    print(f"  {task_id}:")
    print(f"    First 10 avg : {avg_first:+.3f}")
    print(f"    Last  10 avg : {avg_last:+.3f}")
    print(f"    Improvement  : {sign}{improvement:.3f}")


def main():
    print("\n=== merge_curves.py ===")
    print(f"Checkpoint dir : {CHECKPOINT_DIR}")
    print(f"Output         : {OUTPUT_PATH}\n")

    # Dark background matching terminal aesthetic
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#0a0c0f")
    ax.set_facecolor("#0e1117")

    found_any = False
    legend_patches = []

    for task_id, meta in TASKS.items():
        rewards = load_task_rewards(task_id)
        if not rewards:
            continue

        found_any = True
        episodes = list(range(1, len(rewards) + 1))
        smoothed = smooth(rewards, window=5)

        # Raw line (faint)
        ax.plot(
            episodes, rewards,
            alpha=0.2,
            color=meta["color"],
            linewidth=0.8,
            zorder=2,
        )

        # Smoothed line (bold)
        ax.plot(
            episodes, smoothed,
            color=meta["color"],
            linewidth=2.5,
            zorder=3,
        )

        # Start/end markers
        ax.scatter([1], [rewards[0]], color=meta["color"], s=40, zorder=4, alpha=0.6)
        ax.scatter([len(rewards)], [rewards[-1]], color=meta["color"], s=60, zorder=4)

        legend_patches.append(
            mpatches.Patch(color=meta["color"], label=meta["label"])
        )

        print_stats(task_id, rewards)

    if not found_any:
        print("[ERROR] No checkpoints found in", CHECKPOINT_DIR)
        print("  Make sure train.py has run at least one task with --episodes > 0")
        sys.exit(1)

    # Zero line
    ax.axhline(y=0, color="#2a3545", linewidth=1, linestyle="--", zorder=1, alpha=0.8)
    ax.text(
        1, 0.01,
        "zero reward threshold",
        color="#2a3545",
        fontsize=9,
        va="bottom",
    )

    # Grid
    ax.grid(True, alpha=0.1, color="#2a3545")
    ax.set_axisbelow(True)

    # Labels
    ax.set_xlabel("Episode", fontsize=12, color="#6b7d8f", labelpad=8)
    ax.set_ylabel("Episode Reward", fontsize=12, color="#6b7d8f", labelpad=8)
    ax.set_title(
        "LogTriageEnv — GRPO Training Reward Improvement",
        fontsize=14,
        color="#e8f0f8",
        fontweight="bold",
        pad=16,
    )

    # Tick colors
    ax.tick_params(colors="#6b7d8f")
    for spine in ax.spines.values():
        spine.set_edgecolor("#1e2530")

    # Legend
    ax.legend(
        handles=legend_patches,
        loc="lower right",
        fontsize=10,
        facecolor="#0e1117",
        edgecolor="#1e2530",
        labelcolor="#c8d4e0",
    )

    # Annotation
    ax.annotate(
        "Higher reward = agent resolves incident faster with fewer wrong actions",
        xy=(0.02, 0.03),
        xycoords="axes fraction",
        fontsize=9,
        color="#6b7d8f",
        style="italic",
    )

    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight", facecolor="#0a0c0f")
    plt.close()

    print(f"\n[OK] Saved: {OUTPUT_PATH}")
    print("     Open with: start reward_curve.png")
    print("     Push with: git add reward_curve.png && git commit -m 'feat: 3-task reward curve' && git push")


if __name__ == "__main__":
    main()
