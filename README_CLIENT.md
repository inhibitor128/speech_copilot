# Speech Copilot (Hybrid Client-Server Edition)

## Architecture
* **Mode 1 (Home):** Connects to Local Server (192.168.1.42). Private & Free.
* **Mode 2 (Road):** Connects to Venice AI API. Requires Internet & API Key.
* **Working Directory:** /home/jg/apps/speech_copilot

## 1. Setup
### A. Install Dependencies
open terminal in folder and run:
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install requests sounddevice numpy pynput pyautogui pystray pillow
(Note: --system-site-packages is required on Linux so the app can access your OS's native AppIndicator libraries for the system tray menu).

B. Grant Keyboard Permissions (Linux)
To allow the app to listen for hotkeys without needing sudo (which breaks the system tray menu), add your user to the input group:

sudo usermod -aG input $USER
Important: You must reboot your computer (or log out and log back in) after running this command for it to take effect.

C. Add Venice Key (For Road Mode)
The app uses a config.json file to manage settings. When you first run the app, it will generate a config.json file. You can open this file and add your Venice key under the "VENICE_KEY" field. (If you have an old venice_key.txt file, the app will automatically migrate it into the new config file on startup.)

2. Usage
Launch the app:

./start.sh
The app runs entirely in the system tray. The tray icon changes color based on its status:

🟡 Yellow: Checking network connection.
🟢 Green: Connected to Home Server.
🩵 Cyan: Connected to Venice (Road Mode) or forced Venice mode.
🔴 Red: Listening/Recording audio.
🔵 Blue: Processing and sending audio for transcription.
⚫ Gray: Error state (no server, no key, or network issue).
You can right-click the system tray icon to access the context menu:

Force Venice Mode: Manually bypass the home server and use the Venice API.
Quit: Close the app.
3. Server Setup (Headless Machine)
STT is now running Parakeet-TDT-0.6b-v3 (faster than Whisper on the GTX 1660 SUPER).

If you need to restart Parakeet:

ssh -i ~/.ssh/hermes_remote jg@192.168.1.42 "cd ~/parakeet-tdt-0.6b-v3-fastapi-openai && docker compose restart parakeet-gpu"
Old Whisper server (deprecated, kept for reference):

docker run -d --gpus all -p 8000:8000 \
  --name speech-server \
  --restart unless-stopped \
  -v whisper-cache:/root/.cache/huggingface \
  -e WHISPER__MODEL=distil-large-v3 \
  -e WHISPER__COMPUTE_TYPE=int8 \
  fedirz/faster-whisper-server:latest-cuda

4. Troubleshooting

Delay on Road: Cloud transcription is slower than local LAN. This is normal.
Switching Modes: The app checks for the home server only when it launches. If you arrive home, restart the app to switch back to Local Mode.

Auto-Retry Fallback: If you are in Home mode and the server fails or times out during transcription, the app will automatically attempt to transcribe using the Venice API as a fallback (if a key is configured).
Tray Menu Not Working / Hotkey Crashes: Ensure you are running the app without sudo, your user is in the input group, and your virtual environment was created with --system-site-packages.
