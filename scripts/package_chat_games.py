"""Create and verify two complete, secret-free source archives."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
THEME = "services/chat_game_theme.py"
FORBIDDEN = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".temp"}


def build(output):
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Output must be outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    names = sorted(set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode().split("\0")) - {""})
    files = {}
    for name in names:
        path = Path(name)
        if FORBIDDEN.intersection(path.parts) or path.name.startswith(".env"):
            continue
        if path.suffix.lower() in {".zip", ".pyc", ".pyo", ".pem", ".key"}:
            continue
        files[name] = (ROOT / path).read_bytes()
    if THEME not in files:
        raise ValueError("Theme missing")
    archives = []
    for name, pumpkin in (("pumpkin", True), ("rp", False)):
        filename = output / f"GiveawayBot-{name}.zip"
        theme = files[THEME].decode("utf8")
        for value in ("True", "False"):
            theme = theme.replace(f"PUMPKIN_MODE = {value}", f"PUMPKIN_MODE = {pumpkin}")
        with zipfile.ZipFile(filename, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, data in files.items():
                archive.writestr(f"GiveawayBot/{relative}", theme.encode("utf8") if relative == THEME else data)
        with zipfile.ZipFile(filename) as archive:
            assert archive.testzip() is None
            assert len(archive.namelist()) == len(files)
            assert all(not FORBIDDEN.intersection(Path(n).parts) and not Path(n).name.startswith(".env")
                       for n in archive.namelist())
            actual = archive.read(f"GiveawayBot/{THEME}").decode()
            assert f"PUMPKIN_MODE = {pumpkin}" in actual
        archives.append(filename)
        print(f"{filename}: {len(files)} files, sha256={hashlib.sha256(filename.read_bytes()).hexdigest()}")
    with zipfile.ZipFile(archives[0]) as first, zipfile.ZipFile(archives[1]) as second:
        differences = [name for name in first.namelist() if first.read(name) != second.read(name)]
        assert differences == [f"GiveawayBot/{THEME}"], differences
    return archives


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args().output)
