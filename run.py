"""Run the web interface on this computer, with a separate data store for demos."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent


def profiles_root():
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA')
        return (Path(local) if local else Path.home() / 'AppData' / 'Local') / 'XinyuQuantOpen'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'XinyuQuantOpen'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'xinyu-quant-open'


def open_when_started(server, url, done):
    while not done.wait(0.1):
        if server.started:
            webbrowser.open(url)
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Enable configured market data services')
    parser.add_argument('--no-browser', action='store_true', help='Display only the local URL')
    parser.add_argument('--port', type=int, default=0, help='Local port (0 picks a free port)')
    parser.add_argument('--data-dir', type=Path, help='Optional profile root, with separate live and demo directories')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    os.chdir(ROOT)
    os.environ['XINYU_DEMO'] = '0' if args.live else '1'
    profile = (args.data_dir or profiles_root()).expanduser().resolve() / ('live' if args.live else 'demo')
    os.environ['XINYU_DATA_DIR'] = str(profile)
    subprocess.run([sys.executable, str(ROOT / 'frontend' / 'build.py')], check=True, cwd=ROOT)

    import uvicorn

    config = uvicorn.Config('api_server:app', log_level='warning', loop='asyncio')
    server = uvicorn.Server(config)
    done = threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', args.port))
        url = f'http://127.0.0.1:{listener.getsockname()[1]}/#workbench'
        print(f'Xinyu Quant: {url}', flush=True)
        print(f'Profile: {profile}', flush=True)
        if not args.no_browser:
            threading.Thread(target=open_when_started, args=(server, url, done), daemon=True).start()
        try:
            server.run(sockets=[listener])
        finally:
            done.set()
    return 0 if server.started else 1


if __name__ == '__main__':
    raise SystemExit(main())
