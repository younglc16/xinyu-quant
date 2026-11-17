#!/bin/zsh
cd "${0:A:h}" || exit 1
python_path="$(command -v python3.12)"
if [[ -z "$python_path" ]]; then
  for candidate in /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
    if [[ -x "$candidate" ]]; then
      python_path="$candidate"
      break
    fi
  done
fi
if [[ -z "$python_path" ]]; then
  print 'Install Python 3.12 from https://www.python.org/downloads/ first.'
  exit 1
fi
exec "$python_path" start.py "$@"
