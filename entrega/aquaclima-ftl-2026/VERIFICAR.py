"""Verify this delivery folder without external packages."""
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
