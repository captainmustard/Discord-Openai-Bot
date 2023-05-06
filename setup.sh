#!/bin/bash

# Create a virtual environment (optional but recommended)
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install the required Python packages
venv/bin/python3 -m pip -r install requirements.txt
