import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

OUT = Path("reports/v2_final/figures")
OUT.mkdir(parents=True, exist_ok=True)

m4 = pd.read_csv("reports/v2_final/v2_final_s3_posthoc.csv")
m0 = pd.read_csv("reports/v2_baselines/m0_test_s3.csv")

x = m4[["seed", "s3_auprc", "s3_auroc", "s3_brier", "s3_ece"]].merge(
    m0[["seed", "s3_auprc", "s3_auroc", "s3_brier", "s3_ece"]],
    on="seed",
    suffixes=("_m4", "_m0")
)

# 1. AUPRC
plt.figure(figsize=(8,5))
plt.plot(x.seed, x.s3_auprc_m4, marker="o", label="M4")
plt.plot(x.seed, x.s3_auprc_m0, marker="o", label="M0")
plt.xlabel("Seed")
plt.ylabel("S3 AUPRC")
plt.title("S3 AUPRC: M4 vs M0")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "s3_auprc_per_seed.png", dpi=300)
plt.close()

# 2. AUROC
plt.figure(figsize=(8,5))
plt.plot(x.seed, x.s3_auroc_m4, marker="o", label="M4")
plt.plot(x.seed, x.s3_auroc_m0, marker="o", label="M0")
plt.xlabel("Seed")
plt.ylabel("S3 AUROC")
plt.title("S3 AUROC: M4 vs M0")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "s3_auroc_per_seed.png", dpi=300)
plt.close()

# 3. Delta
delta = pd.DataFrame({
    "seed": x.seed,
    "AUPRC": x.s3_auprc_m4 - x.s3_auprc_m0,
    "AUROC": x.s3_auroc_m4 - x.s3_auroc_m0,
})

plt.figure(figsize=(9,5))
plt.axhline(0, linewidth=1)
plt.plot(delta.seed, delta.AUPRC, marker="o", label="AUPRC Δ")
plt.plot(delta.seed, delta.AUROC, marker="o", label="AUROC Δ")
plt.xlabel("Seed")
plt.ylabel("M4 − M0")
plt.title("S3 Performance Difference")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "s3_delta_m4_m0.png", dpi=300)
plt.close()

# 4. Calibration metrics
cal = pd.DataFrame({
    "metric": ["Brier", "ECE"],
    "M4": [x.s3_brier_m4.mean(), x.s3_ece_m4.mean()],
    "M0": [x.s3_brier_m0.mean(), x.s3_ece_m0.mean()],
})

plt.figure(figsize=(7,5))
pos = range(len(cal))
width = 0.35
plt.bar([p-width/2 for p in pos], cal.M4, width, label="M4")
plt.bar([p+width/2 for p in pos], cal.M0, width, label="M0")
plt.xticks(list(pos), cal.metric)
plt.ylabel("Metric value")
plt.title("S3 Calibration Metrics")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "s3_calibration_metrics.png", dpi=300)
plt.close()

print("Created:")
for p in sorted(OUT.glob("*.png")):
    print(p)
