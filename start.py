"""Install the project's Python dependencies and start the local app."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Xinyu Quant requires Python 3.12 for this release.")
    environment = ROOT / '.venv'
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.is_file():
        print('Creating the local Python environment…', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    requirements = ROOT / 'requirements.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = environment / 'xinyu-requirements.sha256'
    if not stamp.exists() or stamp.read_text(encoding='ascii').strip() != digest:
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(requirements)], cwd=ROOT, check=True)
        stamp.write_text(digest + '\n', encoding='ascii')
    command = [str(executable), '-u', str(ROOT / 'run.py'), *sys.argv[1:]]
    if os.name != 'nt':
        os.chdir(ROOT)
        os.execv(str(executable), command)
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
