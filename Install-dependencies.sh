#!/bin/bash

# Create a virtual environment (optional but recommended)
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install the required Python packages
pip install --upgrade pip
pip install discord.py
pip install openai

# Deactivate the virtual environment
deactivate