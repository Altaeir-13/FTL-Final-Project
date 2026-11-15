"""Copy frozen scientific figures and summarize the public package for the FTL deck.

Read-only with respect to the scientific dataset. No acquisition, imputation or refit.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "apresentacao"
FIGURES = OUTPUT / "figuras"
FROZEN = ROOT / "data" / "recovery" / "curated" / "2022_2024_recovery_v1"


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "web" / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def records(name: str) -> list[dict]:
        entry = manifest["files"][name]
        path = manifest_path.parent / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Frozen package integrity failed: {name}")
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    monthly = records("monthly")
    observations = records("observations")
    comparison = records("common_month_metrics")
    figures = {}
    for name in ("temporal_pivots.png", "seasonal_heatmap.png", "rain_context.png"):
        source = FROZEN / name
        if not source.exists():
            source = FIGURES / name  # Versioned exact-byte copies support a clean clone.
        if source.exists():
            destination = FIGURES / name
            if source != destination:
                shutil.copyfile(source, destination)
            figures[name] = {"sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                             "source": f"data/recovery/curated/2022_2024_recovery_v1/{name}",
                             "bytes": source.stat().st_size}
    result = {
        "dataset_version": "2022_2024_recovery_v1",
        "public_package_sha256": manifest["package_sha256"],
        "source_package_sha256": manifest["source_package_sha256"],
        "observations": len(observations),
        "scenes": len({row["scene_id"] for row in observations}),
        "observed_pivot_months": sum(row["monthly_status"] == "ok" for row in monthly),
        "expected_pivot_months": len(monthly),
        "annual_observed": {year: sum(row["month"].startswith(year) and row["monthly_status"] == "ok"
                                      for row in monthly) for year in ("2022", "2023", "2024")},
        "common_metrics": [row for row in comparison if row["comparison"].count("__vs__") == 2
                           and row["status"] == "ok"],
        "figures": figures,
    }
    (OUTPUT / "evidencias-paracatu.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"observations": result["observations"], "scenes": result["scenes"],
                      "observed": result["observed_pivot_months"], "figures": list(figures)}, ensure_ascii=False))

    regional_root = ROOT / "data" / "regions" / "guadalupe-pi"
    if not regional_root.exists():
        regional_root = ROOT / "docs" / "evidencias" / "guadalupe-pi"
    regional_dir = regional_root / "curated" / "v1"
    if regional_dir.exists():
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        summary = json.loads((regional_dir / "summary.json").read_text(encoding="utf-8"))
        for entry in summary["files"].values():
            source = regional_dir / entry["path"]
            if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Regional source integrity failed: {entry['path']}")
        offline = json.loads((regional_root / "offline-verification.json").read_text(encoding="utf-8"))
        if offline != {"status": "identical", "files_checked": 5, "http_requests": 0, "transferred_bytes": 0}:
            raise ValueError("Regional offline verification not complete")
        with (regional_dir / "observations.csv").open(encoding="utf-8", newline="") as stream:
            regional_observations = list(csv.DictReader(stream))
        rows = sorted((r for r in regional_observations if r["pivot_id"] == "PI:5795"), key=lambda r: r["month"])
        fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
        for ax, key, label, color in ((axes[0], "ndvi_median", "NDVI", "#247b75"),
                                       (axes[1], "ndmi_median", "NDMI", "#617d39")):
            ax.scatter(range(len(rows)), [float(r[key]) for r in rows], s=75, color=color)
            ax.set_ylabel(label)
            ax.set_ylim(-1, 1)
            ax.grid(axis="y", alpha=0.2)
        axes[2].bar(range(len(rows)), [float(r["precip_mm"]) for r in rows], color="#6698b2", width=0.5)
        axes[2].set_ylabel("CHIRPS (mm/mês)")
        axes[2].set_xticks(range(len(rows)), [r["month"] for r in rows])
        axes[2].set_xlabel("Meses amostrados, não contíguos (espaçamento igual apenas para comparação)")
        fig.suptitle("Guadalupe/PI: observações reais no pivô ANA 5795\nÍndices por cena aceita e chuva mensal regional")
        destination = FIGURES / "guadalupe-sampled-indices.png"
        fig.savefig(destination, dpi=160)
        plt.close(fig)
        regional_evidence = {
            **summary,
            "offline_verification": offline,
            "execution": json.loads((regional_root / "execution.json").read_text(encoding="utf-8")),
            "slide_text": "Prova exploratória: 29 observações aceitas em 5 pivôs e 6 datas.\nCHIRPS nos 6 meses amostrados. Reprodução offline idêntica.",
            "footer": "29/30 espaços-alvo observados. Amostra não contínua, sem modelos ou métricas de generalização.",
            "notes": "Prova verificada com5arquivos idênticos,zeroHTTP/bytes. Meses2023-01,07,11 e2024-03,07,11,29observações/30tentativas. Grade completa115espaços:29observados25.2%;96.7%refere-se somente30alvos. CHIRPS30/30alvos. Escala/offset C1conferidos com XMLde cada produto,PB05.09/05.10/05.11. Semtreino ou inferência anual completa.",
            "figure": {"path": "figuras/guadalupe-sampled-indices.png",
                       "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()},
        }
        (OUTPUT / "evidencias-regionais.json").write_text(
            json.dumps(regional_evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"region": summary["region_id"], "observations": len(regional_observations),
                          "offline": offline["status"]}))


if __name__ == "__main__":
    main()
