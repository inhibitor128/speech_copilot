#!/bin/bash

# 1. Allow the app to draw on the screen
xhost +si:localuser:root

# 2. Move to the correct folder
cd /home/jg/apps/speech_copilot

# 3. Run the app as a normal user
# NOTE: Your user must be in the 'input' group for hotkeys to work!
./venv/bin/python speech_copilot.py
