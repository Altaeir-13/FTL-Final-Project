"""Windows-friendly entry point for the AquaClima pilot."""

import argparse
import json
import logging
import os
import time
import tomllib
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from aquaclima.features.integration import ANA_SOURCE, SENTINEL_SOURCE, integrate, month_range, read_pivots
from aquaclima.ingestion.chirps import chirps_url, download_precip, extract_precip
from aquaclima.ingestion.sentinel import ASSETS, STAC_ROOT, acquire_crops, search_scenes
from aquaclima.processing.indices import process_indices
from aquaclima.reporting.pilot import plot_timeseries, summarize
from aquaclima.storage.http import AcquisitionError, BudgetError, HttpClient, checksum, read_ledger

LOGGER = logging.getLogger(__name__)
BASIN_SOURCE = "https://portal1.snirh.gov.br/server/rest/services/SFI/Unidades_Automonitoramento_UGRH_MRS/MapServer/0"
COMMANDS = {
    "check-sources": "verifica as três fontes públicas",
    "acquire-pivots": "obtém os polígonos ANA da bacia",
    "search-scenes": "busca cenas STAC e salva a seleção",
    "plan": "exibe o plano a partir da configuração e da busca em cache",
    "acquire-crops": "obtém janelas das quatro bandas selecionadas",
    "download-precip": "obtém GeoTIFFs mensais do CHIRPS",
    "process-indices": "calcula os índices com recortes locais",
    "integrate": "integra os índices à precipitação com arquivos locais",
    "report": "gera gráfico e relatório de aquisição",
    "run": "executa o fluxo completo com aquisição ou em modo offline",
    "history-plan": "consulta inventários mensais e estima a expansão histórica",
    "history-run": "adquire lotes históricos ou reprocessa os lotes offline",
    "history-consolidate": "consolida os lotes históricos locais",
    "history-explore": "gera análise exploratória do histórico local",
    "history-baseline": "ajusta e valida os baselines em períodos cronológicos",
}
REMOTE = {"check-sources", "acquire-pivots", "search-scenes", "acquire-crops", "download-precip"}


@contextmanager
def _data_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".writer.lock").open("ab") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aquaclima", description="Piloto científico AquaClima")
    parser.add_argument("command", choices=COMMANDS, help="; ".join(f"{k}: {v}" for k, v in COMMANDS.items()))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, help="diretório de CSV, gráfico e relatório (padrão: data/curated)")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true", help="exibe o plano local e não usa rede nem grava arquivos")
    parser.add_argument("--offline", action="store_true", help="reprocessa os dados brutos já adquiridos localmente")
    parser.add_argument("--allow-bulk", action="store_true", help="autoriza ampliar o tamanho do piloto")
    return parser


def _options(parser, args):
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    study, limits = config["study"], config["limits"]
    study["start"] = args.start or study["start"]
    study["end"] = args.end or study["end"]
    days = (study["end"] - study["start"]).days + 1
    if days <= 0:
        parser.error("A data inicial precisa ser igual ou anterior à data final.")
    if not 3 <= study["pivot_count"] <= 30 or not 1 <= study["max_scenes"] <= 500:
        parser.error("Configure 3–30 pivôs e 1–500 cenas.")
    if not 0 <= study["max_scene_cloud_pct"] <= 100 or not 0 <= study["min_valid_fraction"] <= 1:
        parser.error("Configure os limites de nuvem (0–100) e de validade (0–1).")
    if any(type(limits[key]) is not int or limits[key] <= 0 for key in (
        "max_transfer_bytes", "max_storage_bytes", "max_downloads",
    )):
        parser.error("Configure limites positivos e inteiros.")
    if not args.allow_bulk and (
        days > 120 or study["pivot_count"] > 5 or study["max_scenes"] > 3
        or limits["max_transfer_bytes"] > 2_000_000_000
    ):
        parser.error("Aquisições acima do piloto exigem --allow-bulk.")
    return study, limits


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _plan_matches(plan: dict, study: dict, pivots: Path) -> bool:
    interval = f"{study['start']}T00:00:00Z/{study['end']}T23:59:59.999999Z"
    return pivots.is_file() and plan.get("request", {}).get("datetime") == interval and plan.get("parameters") == {
        "pivots_sha256": checksum(pivots),
        "max_cloud": study["max_scene_cloud_pct"],
        "max_scenes": study["max_scenes"],
    }


def _print_plan(args, study, limits, pivots, scenes, months):
    scene_plan = _read(scenes) if scenes.is_file() else {}
    matching = _plan_matches(scene_plan, study, pivots)
    document = {
        "command": args.command, "offline": args.offline, "data_dir": str(args.data_dir),
        "study": study, "limits": limits,
        "ana": {"pivots": ANA_SOURCE, "basin": BASIN_SOURCE},
        "sentinel": {
            "search": f"{STAC_ROOT}/search", "assets": ASSETS,
            "selection_cached_for_config": matching,
            "scenes": [
                {"id": item["id"], "date": item["properties"]["datetime"],
                 "urls": {asset: item["assets"][asset]["href"] for asset in ASSETS}}
                for item in scene_plan.get("selected", []) if matching
            ],
        },
        "chirps_monthly": [chirps_url(month) for month in months],
    }
    print(json.dumps(document, ensure_ascii=False, indent=2, default=str))


def _pivots(http, data_dir, study):
    from aquaclima.ingestion.ana import acquire_pivots

    return acquire_pivots(http, data_dir, count=study["pivot_count"])


def _search(http, pivots, data_dir, study):
    return search_scenes(
        http, pivots, data_dir, start=study["start"], end=study["end"],
        max_cloud=study["max_scene_cloud_pct"], max_scenes=study["max_scenes"],
    )


def _probe(http, months):
    def chirps_headers():
        headers = http.head(chirps_url(months[0]))
        return {key: headers[key] for key in ("Content-Type", "Content-Length", "ETag") if key in headers}

    probes = [
        ("ANA pivôs", lambda: http.get_json(ANA_SOURCE, params={"f": "json"})["name"]),
        ("ANA bacia", lambda: http.get_json(BASIN_SOURCE, params={"f": "json"})["name"]),
        ("Sentinel-2", lambda: http.get_json(SENTINEL_SOURCE)["id"]),
        ("CHIRPS", chirps_headers),
    ]
    results = {}
    success = True
    for name, operation in probes:
        try:
            results[name] = {"status": "ok", "response": operation()}
        except (AcquisitionError, KeyError, ValueError) as exc:
            results[name] = {"status": "failed", "error": str(exc)}
            success = False
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if success else 1


def _run(args, http, study, months, paths) -> int:
    start = time.perf_counter()
    data_dir = args.data_dir
    output = args.output_dir
    baseline = len(read_ledger(data_dir / "acquisition.jsonl"))
    pivots, scenes, crops, rain, indices, precip = paths
    failures = []

    def stage(name, operation):
        LOGGER.info("%s", name)
        try:
            return operation()
        except (AcquisitionError, BudgetError, OSError, ValueError, KeyError) as exc:
            LOGGER.error("%s: %s", name, exc)
            failures.append(f"{name}: {exc}")
            return None

    if args.offline:
        missing = [path for path in (pivots, scenes, crops, rain) if not path.is_file()]
        if missing:
            raise ValueError(f"Arquivos locais obrigatórios ausentes: {', '.join(map(str, missing))}")
        if not _plan_matches(_read(scenes), study, pivots) or _read(crops)["plan_sha256"] != checksum(scenes):
            raise ValueError("O inventário local Sentinel-2 não corresponde aos pivôs ou à configuração informada.")
        if not set(months).issubset(_read(rain)["months"]):
            raise ValueError("O inventário local CHIRPS não corresponde ao intervalo informado.")
        acquired_pivots, selected, cropped, downloaded = pivots, scenes, crops, rain
    else:
        acquired_pivots = stage("Pivôs ANA", lambda: _pivots(http, data_dir, study))
        selected = stage("Busca Sentinel-2", lambda: _search(http, acquired_pivots, data_dir, study)) if acquired_pivots else None
        cropped = stage("Janelas Sentinel-2", lambda: acquire_crops(http, acquired_pivots, selected, data_dir)) if selected else None
        downloaded = stage("Precipitação CHIRPS", lambda: download_precip(http, data_dir, months))

    computed = stage("Índices espectrais", lambda: process_indices(
        acquired_pivots, cropped, data_dir, min_valid_fraction=study["min_valid_fraction"],
    )) if cropped else None
    sampled = stage("Amostragem CHIRPS", lambda: extract_precip(
        acquired_pivots, downloaded, data_dir, months=months,
    )) if acquired_pivots and downloaded else None
    table = stage("Integração", lambda: integrate(acquired_pivots, computed, sampled, months, output)) if acquired_pivots else None
    if table:
        stage("Gráfico temporal", lambda: plot_timeseries(table, output))
    scene_info = _read(selected) if selected else {}
    pivot_count = len(read_pivots(acquired_pivots)) if acquired_pivots else 0
    report = summarize(
        data_dir, output, table_path=table, elapsed=time.perf_counter() - start, run_start=baseline,
        failures=failures, requested_months=months, pivots=pivot_count, scenes=scene_info, offline=args.offline,
    )
    print(report)
    result = _read(report)
    if failures or not result["spectral_status"].get("ok") or result["precip_status"] != {"ok": result["observations"]}:
        LOGGER.warning("Fluxo incompleto ou sem observações aceitas; consulte o relatório.")
        return 1
    return 0


def _dispatch(args, http, study, months, paths):
    pivots, scenes, crops, rain, indices, precip = paths
    data_dir = args.data_dir
    output = args.output_dir
    if args.command == "run":
        return _run(args, http, study, months, paths)
    if args.command == "check-sources":
        return _probe(http, months)
    if args.command == "report":
        table = output / "observacoes.csv"
        plot_timeseries(table, output)
        print(summarize(
            data_dir, output, table_path=table, elapsed=0, run_start=0, failures=[],
            requested_months=months, pivots=len(read_pivots(pivots)), scenes=_read(scenes), offline=args.offline,
        ))
        return 0
    operations = {
        "acquire-pivots": lambda: _pivots(http, data_dir, study),
        "search-scenes": lambda: _search(http, pivots, data_dir, study),
        "acquire-crops": lambda: acquire_crops(http, pivots, scenes, data_dir),
        "download-precip": lambda: download_precip(http, data_dir, months),
        "process-indices": lambda: process_indices(pivots, crops, data_dir, min_valid_fraction=study["min_valid_fraction"]),
        "integrate": lambda: integrate(
            pivots, indices, extract_precip(pivots, rain, data_dir, months=months), months, output,
        ),
    }
    print(operations[args.command]())
    return 0


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args.data_dir = args.data_dir.resolve()
    args.config = args.config or Path("configs/history.toml" if args.command.startswith("history-") else "configs/pilot.toml")
    if args.command.startswith("history-"):
        from aquaclima.history import execute

        try:
            if args.dry_run:
                return execute(args)
            with _data_lock(args.data_dir):
                return execute(args)
        except (AcquisitionError, BudgetError, OSError, ValueError, KeyError) as exc:
            LOGGER.error("%s", exc)
            return 1
    args.output_dir = (args.output_dir or args.data_dir / "curated").resolve()
    root = args.data_dir
    paths = (
        root / "processed/pivots.geojson", root / "raw/sentinel/scenes.json", root / "raw/sentinel/crops.json",
        root / "raw/chirps/manifest.json", root / "processed/indices.csv", root / "processed/precip_monthly.csv",
    )
    try:
        study, limits = _options(parser, args)
        months = month_range(study["start"], study["end"])
        if args.offline and args.command in REMOTE:
            parser.error(f"{args.command} requer acesso às fontes. Use run --offline para reprodução.")
        if args.dry_run or args.command == "plan":
            _print_plan(args, study, limits, paths[0], paths[1], months)
            return 0
        with _data_lock(root):
            if not args.offline and (args.command in REMOTE or args.command == "run"):
                with HttpClient(ledger=root / "acquisition.jsonl", **limits) as http:
                    return _dispatch(args, http, study, months, paths)
            return _dispatch(args, None, study, months, paths)
    except (AcquisitionError, BudgetError, OSError, ValueError, KeyError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
