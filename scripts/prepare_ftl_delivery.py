"""Assemble and verify the reviewed FTL delivery using only existing local files.

No science processing, acquisitions, external requests or dependency installation.
Run from the repository root. ZIP entries have fixed timestamps for repeatability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "entrega/aquaclima-ftl-2026"
ARCHIVE = DEST.parent / "aquaclima-ftl-2026.zip"
CODE = "ad107d0c29c63ad9eb9f91a5970d96906676e3df"
PUBLIC = "https://altaeir-13.github.io/FTL-Final-Project/"
AUDIT = ROOT / "docs/evidencias/release-publica"
COPY = {
    "01-relatorio-cientifico-aquaclima.pdf": "docs/relatorio-final-ftl.pdf",
    "02-apresentacao-editavel.pptx": "docs/apresentacao/aquaclima-ftl-fase7.pptx",
    "03-apresentacao-apoio.pdf": "docs/apresentacao/aquaclima-ftl-fase7.pdf",
    "04-roteiro-apresentacao-e-demo.md": "docs/roteiro-final-ftl.md",
    "05-ficha-exemplo-guadalupe.pdf": "docs/evidencias/release-publica/ficha-evidencias-guadalupe.pdf",
    "06-ficha-exemplo-paracatu.pdf": "docs/evidencias/release-publica/ficha-evidencias-paracatu.pdf",
    "CHECKLIST-ENTREGA.md": "docs/checklist-entrega-ftl.md",
    "AUDITORIA-DE-LANCAMENTO.md": "docs/release-final-ftl.md",
    "REVISAO-APRESENTACAO.md": "docs/revisao-apresentacao-release.md",
    "evidencias/playwright-publico.json": "docs/evidencias/release-publica/playwright-publico.json",
    "evidencias/integridade-publica.json": "docs/evidencias/release-publica/integridade-publica.json",
    "evidencias/capturas-publicas.json": "docs/evidencias/release-publica/capturas-publicas.json",
    "evidencias/verificacao-fichas-publicas.json": "docs/evidencias/release-publica/verificacao-fichas-publicas.json",
    "evidencias/fidelidade-relatorio.json": "docs/evidencias/release-publica/fidelidade-relatorio.json",
}
CAPTURES = ["territorio-desktop.png", "territorio-mobile.png", "investigacao-paracatu-desktop.png",
            "investigacao-guadalupe-desktop.png", "investigacao-guadalupe-mobile.png",
            "investigacao-guadalupe-mobile-imagens.png", "demonstracao-publica-desktop.png", "ficha-guadalupe-previa.png"]
COPY.update({f"evidencias/{name}": f"docs/evidencias/release-publica/{name}" for name in CAPTURES})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: str | Path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def write(name: str, text: str):
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def portable_markdown(name: str, source: str, public_paths: set[str]):
    """Keep delivery links local when included; point source-only links at GitHub."""
    reverse = {str((ROOT/value).resolve()): key for key,value in COPY.items()}
    reverse[str((DEST/"README.md").resolve())] = "README.md"
    def replace(match):
        target = match.group(1)
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path or target.startswith("#"):
            return match.group(0)
        original = (ROOT/source).parent / parsed.path
        path = original.resolve()
        if str(path) in reverse:
            result = posixpath.relpath(reverse[str(path)], posixpath.dirname(name) or ".")
        elif path.is_relative_to(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            revision = CODE if relative in public_paths else "codex/aquaclima-release-ftl"
            result = f"https://github.com/Altaeir-13/FTL-Final-Project/blob/{revision}/{quote(relative)}"
        else:
            raise ValueError(f"Document link outside the repository: {target}")
        if parsed.fragment:
            result += "#" + parsed.fragment
        return "](" + result + ")"
    write(name,re.sub(r"\]\(([^\s)]+)\)",replace,(ROOT/source).read_text(encoding="utf-8")))


def verify():
    entries = (DEST / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    expected = {"SHA256SUMS.txt"}
    for entry in entries:
        checksum, name = entry.split("  ", 1)
        path = (DEST / name).resolve()
        if not path.is_relative_to(DEST.resolve()) or not path.is_file() or sha(path) != checksum:
            raise ValueError(f"Delivery checksum mismatch: {name}")
        expected.add(name)
    actual = {p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file()}
    if expected != actual:
        raise ValueError("Undeclared delivery file or missing file.")
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt ZIP archive.")
        for name in sorted(actual):
            if archive.read(f"{DEST.name}/{name}") != (DEST / name).read_bytes():
                raise ValueError(f"ZIP bytes differ: {name}")
        if len(archive.namelist()) != len(actual):
            raise ValueError("Unexpected ZIP member.")
    archive_sum = (DEST.parent/"SHA256SUMS.txt").read_text(encoding="utf-8").strip()
    if archive_sum != f"{sha(ARCHIVE)}  {ARCHIVE.name}":
        raise ValueError("ZIP checksum sidecar differs from the reviewed archive.")
    return len(actual)


def assemble():
    tests = read("docs/evidencias/release-publica/playwright-publico.json")
    public = read("docs/evidencias/release-publica/integridade-publica.json")
    captures = read("docs/evidencias/release-publica/capturas-publicas.json")
    report = read("docs/evidencias/release-publica/fidelidade-relatorio.json")
    if tests["stats"]["expected"] != 25 or any(tests["stats"][key] for key in ["skipped", "unexpected", "flaky"]):
        raise ValueError("Public test run is not fully approved.")
    if not public["all_served_files_identical"] or len(public["files"]) != 24 or captures["status"] != "passed":
        raise ValueError("Public integrity or browser capture is incomplete.")
    if report["missing_text_blocks"] != 0 or sha(ROOT / report["output"]) != report["pdf_sha256"]:
        raise ValueError("Scientific report fidelity record is stale.")
    for output in captures["outputs"]:
        if sha(AUDIT / output["file"]) != output["sha256"]:
            raise ValueError(f"Stale capture checksum: {output['file']}")
    generated = {"README.md", "LINKS-PUBLICOS.md", "VERIFICAR.py", "VERSAO-E-INTEGRIDADE.json", "SHA256SUMS.txt"}
    known = set(COPY) | generated
    if DEST.exists():
        unknown = [p for p in DEST.rglob("*") if p.is_file() and p.relative_to(DEST).as_posix() not in known]
        if unknown:
            raise ValueError(f"Refusing to overwrite a delivery with undeclared files: {unknown}")
    DEST.mkdir(parents=True, exist_ok=True)
    public_paths=set(subprocess.run(["git","ls-tree","-r","--name-only",CODE],cwd=ROOT,check=True,capture_output=True,text=True,encoding="utf-8").stdout.splitlines())
    for name, source in COPY.items():
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".md"):
            portable_markdown(name,source,public_paths)
        else:
            shutil.copyfile(ROOT / source, target)
    links = [f"# Links públicos — AquaClima\n\nVersão 1.1.0 · main `{CODE}` · referência 17/11/2026.\n",
             f"- [Aplicação publicada]({PUBLIC})",
             "- [Repositório](https://github.com/Altaeir-13/FTL-Final-Project)",
             "- [Deployment aprovado](https://github.com/Altaeir-13/FTL-Final-Project/actions/runs/44067496065)",
             "- [PR #3 integrado](https://github.com/Altaeir-13/FTL-Final-Project/pull/3)"]
    for selection in captures["investigations"]:
        url = selection["public_investigation_url"].split("#", 1)[0] + "#investigacao"
        links.append(f"- [{selection['region']} · {selection['pivot']} · {selection['a']} / {selection['b']}]({url})")
    write("LINKS-PUBLICOS.md", "\n".join(links) + "\n")
    write("README.md", """# AquaClima — entrega do Capstone FTL

Autor: **Randerson Sousa de Sá Nunes**. Referência: **17/11/2026**. Prazo: **24/11/2026**.
Aplicação **1.1.0**, release proposta **v1.1.0-ftl**, preparada para revisão. Não constitui submissão oficial.

| Arquivo | Uso |
|---|---|
| 01-relatorio-cientifico-aquaclima.pdf | Relatório completo, 13 páginas A4, texto selecionável, figuras e referências |
| 02-apresentacao-editavel.pptx | Mestre editável, oito slides |
| 03-apresentacao-apoio.pdf | Backup raster de oito páginas; sem texto selecionável |
| 04-roteiro-apresentacao-e-demo.md | Fala de cinco minutos, demonstração de três minutos e perguntas da banca |
| 05-ficha-exemplo-guadalupe.pdf | Ficha real do site público, cenas 18/07/2023 e 22/07/2024, quatro páginas |
| 06-ficha-exemplo-paracatu.pdf | Ficha real do site público, agregados julho/2023 e julho/2024, cinco páginas |
| LINKS-PUBLICOS.md | Site, código, deployment e investigações reproduzíveis |
| CHECKLIST-ENTREGA.md | Verificações concluídas e tarefas do responsável |
| AUDITORIA-DE-LANCAMENTO.md / REVISAO-APRESENTACAO.md | Escopo, limites e evidências da revisão |
| evidencias/ | Resultados por cenário, hashes, fidelidade de documentos e capturas autênticas |
| VERSAO-E-INTEGRIDADE.json / SHA256SUMS.txt | Proveniência da versão e checksums individuais |
| VERIFICAR.py | Verificação local da pasta, apenas biblioteca padrão Python |

Os PDFs e o PPTX abrem sem backend, rasters privados ou APIs pagas. Os links de demonstração acessam o site público. Nos documentos Markdown, links para arquivos incluídos são locais; referências adicionais apontam para suas versões no GitHub e exigem conexão. Nenhum arquivo de aquisição científica está incluído.

Paracatu é o estudo científico concluído. Guadalupe é prova exploratória, sem modelo regional validado. Caxias é origem e motivação, sem observações processadas. As fichas não comprovam causas, falhas de irrigação, economia de água ou ganhos financeiros. A data de geração das fichas é distinta das datas observadas.

Para conferir a pasta isoladamente, execute `python VERIFICAR.py`. Com sha256sum disponível: `sha256sum --check SHA256SUMS.txt`. O checksum não se inclui em si próprio. O ZIP adjacente contém exatamente esta pasta e tem checksum separado no diretório entrega/.

O responsável ainda deve confirmar as regras oficiais de submissão, revisar os materiais e o rascunho de release, abrir o PPTX no editor/projetor, ensaiar com cronômetro, congelar a entrega em 23/11 e submeter oficialmente em 24/11, guardando o comprovante. A verificação de 390 px em navegador não substitui teste em aparelho físico.
""")
    write("VERIFICAR.py", '''"""Verify this delivery folder without external packages."""
from pathlib import Path
import hashlib
root = Path(__file__).resolve().parent
expected = {"SHA256SUMS.txt"}
for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
    checksum, name = line.split("  ", 1)
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise SystemExit(f"Falha de integridade: {name}")
    expected.add(name)
actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
if actual != expected:
    raise SystemExit("Arquivo extra ou ausente na pasta.")
print(f"Entrega íntegra: {len(actual)} arquivos conferidos.")
''')
    files = [{"path":p.relative_to(DEST).as_posix(), "bytes":p.stat().st_size, "sha256":sha(p)}
             for p in sorted(DEST.rglob("*")) if p.is_file() and p.name not in {"VERSAO-E-INTEGRIDADE.json", "SHA256SUMS.txt"}]
    manifest = {"reference_date":"2026-11-17", "author":"Randerson Sousa de Sá Nunes", "system_version":"1.1.0",
                "proposed_release":"v1.1.0-ftl", "release_status":"prepared_for_review", "official_submission":False,
                "deployed_code_commit":CODE, "materials_branch":"codex/aquaclima-release-ftl", "deployment_run":44067496065,
                "public_url":PUBLIC, "build_artifact_sha256":public["verified_build_artifact_sha256"],
                "scientific_packages":{"paracatu":public["paracatu_package_sha256"], "guadalupe":public["regional_package_sha256"]},
                "public_tests":{"passed":25,"skipped":0,"failed":0,"flaky":0,"duration_ms":tests["stats"]["duration"],"local_server":False},
                "scope":"Existing scientific results preserved. Reports and files prepared for human review. No acquisition, training or new features.",
                "files":files, "manifest_scope":"Payload files above exclude this manifest and SHA256SUMS.txt; SHA256SUMS includes this manifest."}
    write("VERSAO-E-INTEGRIDADE.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    names=sorted(p.relative_to(DEST).as_posix() for p in DEST.rglob("*") if p.is_file() and p.name!="SHA256SUMS.txt")
    write("SHA256SUMS.txt", "".join(f"{sha(DEST/name)}  {name}\n" for name in names))
    with zipfile.ZipFile(ARCHIVE,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(p for p in DEST.rglob("*") if p.is_file()):
            member=zipfile.ZipInfo(f"{DEST.name}/{path.relative_to(DEST).as_posix()}", date_time=(2026,11,17,0,0,0))
            member.compress_type=zipfile.ZIP_DEFLATED
            member.external_attr=0o100644 << 16
            archive.writestr(member,path.read_bytes())
    (DEST.parent/"SHA256SUMS.txt").write_text(f"{sha(ARCHIVE)}  {ARCHIVE.name}\n",encoding="utf-8",newline="\n")
    return verify()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only",action="store_true")
    arguments=parser.parse_args()
    count=verify() if arguments.verify_only else assemble()
    print(json.dumps({"files":count,"zip":"entrega/aquaclima-ftl-2026.zip","zip_sha256":sha(ARCHIVE)},ensure_ascii=False))
