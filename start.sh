#!/bin/bash

# Only install requirements if file changed or doesn't exist
if [[ -f requirements.txt ]] && [[ ! -f .local/.req_installed || requirements.txt -nt .local/.req_installed ]]; then
    echo "Requirements changed - installing..."
    pip install --disable-pip-version-check -U --prefix .local -r requirements.txt
    touch .local/.req_installed
else
    echo "Requirements unchanged - skipping installation"
fi

# Start the bot
python main.py