"""Render saved evaluation evidence. This script never loads or runs a model."""

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "artifacts/evaluation.json").read_text(encoding="utf-8"))
model = json.loads((ROOT / "artifacts/model.json").read_text(encoding="utf-8"))
assets = ROOT / "docs/assets"
assets.mkdir(parents=True, exist_ok=True)
names = {"fifo": "FIFO", "spt": "Shortest processing time", "mwkr": "Most work remaining",
         "best_of_rules": "Best of three rules (oracle)", "cp_sat": "CP-SAT incumbent"}
summary = report["test"]["summary"]
rows = [(key, summary["paired"][key]) for key in names]

fig, ax = plt.subplots(figsize=(10.4, 4.9), layout="constrained")
fig.patch.set_facecolor("#0f0f0f")
ax.set_facecolor("#0f0f0f")
for index, (method, pair) in enumerate(rows):
    mean = pair["mean_improvement_percent"]
    low, high = pair["mean_improvement_ci95_percent"]
    color = "#67dfb1" if mean >= 0 else "#e4b275"
    ax.barh(index, mean, height=0.5, color=color, alpha=0.85)
    ax.errorbar(mean, index, xerr=[[mean - low], [high - mean]], color="#f3f3f3", capsize=4, linewidth=1.1)
ax.set_yticks(range(len(rows)), [names[key] for key, _ in rows])
ax.invert_yaxis()
ax.axvline(0, color="#999", linewidth=1)
ax.set_xlim(-15, 30)
ax.set_xlabel("Makespan reduction vs reference (%) · positive favors the learned policy", color="#ddd", labelpad=12)
ax.set_title("QueueCraft / frozen synthetic test, 72 instances", loc="left", color="#fff", pad=18, fontsize=16)
ax.tick_params(colors="#ddd", labelsize=10)
for spine in ax.spines.values():
    spine.set_color("#333")
ax.grid(axis="x", color="#444", alpha=0.4)
ax.set_axisbelow(True)
fig.text(0.01, -0.04, "Whiskers: paired 95% bootstrap intervals over instances, conditional on one selected artifact.\nNo real-factory validation. CP-SAT also ran faster on these small cases.", color="#aaa", fontsize=9)
fig.savefig(assets / "frozen-test-comparison.png", dpi=180, bbox_inches="tight")
fig.savefig(assets / "frozen-test-comparison.svg", bbox_inches="tight")
plt.close(fig)

table = ["# Measured results", "", "Evidence date: 2026-10-28. The selected artifact uses three CPU-fit configurations and development-only selection. No frozen-test result was used for training or configuration selection.", "", "## Training", "", f"- Training instances: {model['training_summary']['instances']}; development: {model['training_summary']['development_instances']}.", f"- Labels: {model['training_summary']['label_rows']}; features: {len(model['feature_names'])}; model fits: {model['training_summary']['fits']}.", "- All 240 training teachers proved optimal within the configured budget and passed serial replay. The earlier 18-case feasibility gate also passed.", "- The target is negative normalized forced-action rollout regret. Several equally good candidate actions receive the same target.", "", "![Paired frozen-test comparison](assets/frozen-test-comparison.png)", "", "## Frozen test: 72 instances", "", "Reduction is the average of `100 * (reference_makespan - learned_makespan) / reference_makespan` over paired instances. Positive values favor ML. It is not a ratio of aggregate mean durations.", "", "| Reference | Mean reduction | Paired 95% interval | ML wins / ties / losses |", "|---|---:|---:|---:|"]
for key, pair in rows:
    low, high = pair["mean_improvement_ci95_percent"]
    table.append(f"| {names[key]} | {pair['mean_improvement_percent']:+.2f}% | [{low:+.2f}%, {high:+.2f}%] | {pair['wins']} / {pair['ties']} / {pair['losses']} |")
table += ["", "The FIFO and best-of-rules intervals include zero. These results do not establish an advantage over those comparisons. The best-of-rules row chooses the best of the three complete heuristic schedules separately for each problem; it is an oracle comparison, not one deployed rule.", "", "## Runtime and reference coverage", "", "End-to-end method time includes construction/features/prediction and schedule validation. It excludes HTTP, plotting/replay and artifact loading. Teacher generation and training are separate costs.", "", "| Split | Method | Valid schedules | Proven optima | Median method time |", "|---|---|---:|---:|---:|"]
for split in ("test", "ood"):
    for key, entry in report[split]["summary"]["methods"].items():
        table.append(f"| {split} | {key} | {entry['valid_count']} / {report[split]['summary']['count']} | {entry['optimal_count']} | {entry['median_wall_ms']:.2f} ms |")
table += ["", "CP-SAT produced a better schedule and lower median method time than the learned policy on these small test sets. QueueCraft does not currently demonstrate solver acceleration. Its demonstrated contribution is a reproducible learned-dispatch experiment and an inspectable comparison workbench.", "", "## Larger-size check", "", "The 36 larger instances have seven jobs and six machines, outside the training size range of three to six jobs and three to five machines. They use the same three duration families; this tests size transfer, not an unseen factory or a wholly new noise/process distribution.", "", "| Reference | Mean reduction | ML wins / ties / losses | Paired count |", "|---|---:|---:|---:|"]
for key, pair in report["ood"]["summary"]["paired"].items():
    table.append(f"| {names[key]} | {pair['mean_improvement_percent']:+.2f}% | {pair['wins']} / {pair['ties']} / {pair['losses']} | {pair['count']} |")
table += ["", "One of the 36 larger CP-SAT solves returned no incumbent within 0.5 seconds. That case is excluded from the paired CP-SAT comparison and remains visible in the saved instance records. UNKNOWN is not INFEASIBLE. Comparisons use returned incumbents; a proof of optimum depends on each recorded solver status.", "", "## Limitations", "", "Synthetic, fully known static instances only. No measured manufacturing savings, deadlines, setup/changeover cost, materials, machine maintenance, unexpected failures or human scheduling validation. The learned policy's worst main-test loss against FIFO is 25.66% longer makespan. A small experimental scorer is not a production-control system.", "", "Bootstrap intervals describe paired-instance sampling conditional on one selected artifact. They do not account for training-seed variation. Candidate configurations use different seeds and hyperparameters; they are not a controlled seed-stability experiment.", "", "## Evidence files", "", "- `artifacts/protocol.json`: splits, budgets, candidates and selection objective, saved before fitting.", "- `data/instances.json`: all generated instances and exact relabeling-invariant group IDs.", "- `artifacts/training_evidence.json`: label counts and teacher/replay outcomes.", "- `artifacts/model.json`, `scorer.joblib`: selected parameters, version, artifact hash and weights.", "- `artifacts/evaluation.json`: frozen-test and larger-size per-instance results, runtimes, validation and reference status.", "", "Do not select a new model using these frozen results. A new improvement study needs a fresh evaluation protocol.", ""]
(ROOT / "docs/RESULTS.md").write_text("\n".join(table), encoding="utf-8")
with (assets / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["split", "reference", "paired_count", "wins", "ties", "losses", "mean_makespan_reduction_percent", "ci95_low", "ci95_high"])
    for split in ("test", "ood"):
        for key, pair in report[split]["summary"]["paired"].items():
            writer.writerow([split, key, pair["count"], pair["wins"], pair["ties"], pair["losses"], pair["mean_improvement_percent"], *pair["mean_improvement_ci95_percent"]])
print("Rendered saved evidence only: RESULTS.md, PNG, SVG and CSV. No inference or training.")
