import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import sounddevice as sd
import numpy as np
from pynput import keyboard as pynput_keyboard
import threading
import pyautogui
import queue
import time
import sys
import io
import requests
import wave
import os
import json

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "HOME_SERVER_IP": "192.168.1.42",
    "HOME_SERVER_PORT": "5092",
    "VENICE_URL": "https://api.venice.ai/api/v1/audio/transcriptions",
    "VENICE_MODEL": "openai/whisper-large-v3",
    "HOTKEY": "<ctrl>+<alt>+<space>",
    "MIC_PRIORITIES": ["MV7+", "Shure", "Samson", "Blue", "Webcam", "USB", "HDA"]
}

class SpeechCopilot:
    def __init__(self):
        self.load_config()
        self.is_recording = False
        self.audio_data = []
        self.stream = None
        self.device_index = None
        self.device_name = "Default"
        self.active_sample_rate = 16000 
        
        self.mode = "CHECKING"
        self.venice_key = self.load_venice_key()

        # Initialize Tray Icon
        self.icon_image = self.create_image("yellow")
        self.icon = pystray.Icon("SpeechCopilot", self.icon_image, "Copilot: Checking...", menu=pystray.Menu(
            item('Force Venice Mode', self.force_venice_mode),
            item('Quit', self.quit_app)
        ))
        
        # Start background setup
        threading.Thread(target=self.setup_client, daemon=True).start()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            self.config = DEFAULT_CONFIG
        else:
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
                
        self.HOME_SERVER_IP = self.config.get("HOME_SERVER_IP", DEFAULT_CONFIG["HOME_SERVER_IP"])
        self.HOME_SERVER_PORT = self.config.get("HOME_SERVER_PORT", DEFAULT_CONFIG["HOME_SERVER_PORT"])
        self.HOME_URL = f"http://{self.HOME_SERVER_IP}:{self.HOME_SERVER_PORT}/v1/audio/transcriptions"
        self.VENICE_URL = self.config.get("VENICE_URL", DEFAULT_CONFIG["VENICE_URL"])
        self.VENICE_MODEL = self.config.get("VENICE_MODEL", DEFAULT_CONFIG["VENICE_MODEL"])
        self.HOTKEY = self.config.get("HOTKEY", DEFAULT_CONFIG["HOTKEY"])
        self.MIC_PRIORITIES = self.config.get("MIC_PRIORITIES", DEFAULT_CONFIG["MIC_PRIORITIES"])

    def load_venice_key(self):
        # First try to load from config.json if we want to migrate
        if "VENICE_KEY" in self.config and self.config["VENICE_KEY"]:
            return self.config["VENICE_KEY"]
            
        # Fallback to venice_key.txt
        try:
            with open("venice_key.txt", "r") as f:
                key = f.read().strip()
                # Migrate to config
                self.config["VENICE_KEY"] = key
                with open(CONFIG_FILE, "w") as f_out:
                    json.dump(self.config, f_out, indent=4)
                return key
        except FileNotFoundError:
            return None

    def create_image(self, color):
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Draw a circle
        dc.ellipse(
            [(0, 0), (width, height)],
            fill=color)
        return image

    def update_icon(self, color, hover_text):
        if self.icon:
            self.icon.icon = self.create_image(color)
            self.icon.title = hover_text

    def find_best_mic(self):
        try:
            devices = sd.query_devices()
        except Exception:
            return None, "System Default"

        print("\n=== AUDIO DEVICES ===")
        for device in devices:
            if device['max_input_channels'] > 0:
                print(f"{device['index']}: {device['name']}")
        print("=====================\n")
        
        for priority in self.MIC_PRIORITIES:
            for device in devices:
                if device['max_input_channels'] > 0:
                    if priority.lower() in device['name'].lower():
                        print(f"✅ Mic Selected: {device['name']}")
                        return device['index'], device['name']
        return None, "System Default"

    def setup_client(self):
        # 1. Select Mic
        self.device_index, self.device_name = self.find_best_mic()
        disp_name = self.device_name.replace("Microsoft", "").strip()[:10]
        
        # 2. Network Check (Home vs Road)
        self.update_icon("yellow", f"Checking Net... ({disp_name})")
        
        self.check_network_and_set_mode()

        # 3. Hotkey
        try:
            self.hotkey_listener = pynput_keyboard.GlobalHotKeys({
                self.HOTKEY: self.toggle_recording
            })
            self.hotkey_listener.start()
        except Exception as e:
            print(f"ERROR starting hotkey listener: {e}")

    def check_network_and_set_mode(self, force_venice=False):
        disp_name = self.device_name.replace("Microsoft", "").strip()[:10]
        if force_venice:
            if self.venice_key:
                self.mode = "VENICE"
                print("🌍 Forced Venice AI mode.")
                self.update_icon("cyan", f"Venice (Forced) ({disp_name})")
            else:
                self.mode = "ERROR"
                print("❌ Cannot force Venice AI: No key found.")
                self.update_icon("gray", "Error: No Venice Key")
            return

        try:
            # Try to ping Home Server (fast timeout)
            requests.get(f"http://{self.HOME_SERVER_IP}:{self.HOME_SERVER_PORT}/docs", timeout=1)
            self.mode = "HOME"
            print(f"✅ Connected to Home Server at {self.HOME_SERVER_IP}")
            self.update_icon("green", f"Home Server ({disp_name})")
        except:
            # Fallback to Venice
            if self.venice_key:
                self.mode = "VENICE"
                print("🌍 Home unavailable. Switched to Venice AI.")
                self.update_icon("cyan", f"Venice (Road) ({disp_name})")
            else:
                self.mode = "ERROR"
                print("❌ Home unreachable and no Venice key found.")
                self.update_icon("gray", "Error: No Server/Key")

    def force_venice_mode(self, icon, item):
        self.check_network_and_set_mode(force_venice=True)

    def quit_app(self, icon, item):
        if self.stream:
            self.stream.stop()
            self.stream.close()
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()
        if self.icon:
            self.icon.stop()
        os._exit(0)

    # --- Audio Logic ---
    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if self.mode == "ERROR":
            print("Cannot record: No server available.")
            return

        self.is_recording = True
        self.update_icon("red", "Listening...")
        self.audio_data = []
        
        # Auto-Negotiation (Laptop Logic)
        rates_to_try = [16000, 48000, 44100] 
        
        for rate in rates_to_try:
            try:
                self.stream = sd.InputStream(
                    device=self.device_index, 
                    callback=self.audio_callback, 
                    channels=1, 
                    samplerate=rate
                )
                self.stream.start()
                self.active_sample_rate = rate 
                print(f"Connected at {rate}Hz")
                return 
            except Exception:
                continue
        
        self.update_icon("gray", "Mic Error")

    def stop_recording(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.update_icon("blue", "Sending...")
        threading.Thread(target=self.transcribe_and_type, daemon=True).start()

    def audio_callback(self, indata, frames, time, status):
        if self.is_recording:
            volume_norm = np.linalg.norm(indata) * 10
            if volume_norm > 0.5:
                sys.stdout.write("|" * int(min(volume_norm, 50)))
                sys.stdout.flush()
            self.audio_data.append(indata.copy())

    def process_venice_request(self, wav_buffer):
        files = {'file': ('audio.wav', wav_buffer, 'audio/wav')}
        data = {'model': self.VENICE_MODEL} 
        headers = {'Authorization': f'Bearer {self.venice_key}'}
        return requests.post(self.VENICE_URL, headers=headers, files=files, data=data, timeout=30)

    def transcribe_and_type(self):
        print("") 
        if not self.audio_data:
            self.reset_ui()
            return

        # Prepare Audio
        audio_np = np.concatenate(self.audio_data, axis=0).flatten()
        audio_int16 = (audio_np * 32767).astype(np.int16)
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) 
            wf.setframerate(self.active_sample_rate)
            wf.writeframes(audio_int16.tobytes())

        # --- MODE SWITCHING LOGIC ---
        try:
            response = None
            if self.mode == "HOME":
                # --- HOME SERVER REQUEST ---
                wav_buffer.seek(0)
                files = {'file': ('audio.wav', wav_buffer, 'audio/wav')}
                data = {'model': 'distil-large-v3'}
                
                try:
                    response = requests.post(self.HOME_URL, files=files, data=data, timeout=30)
                    response.raise_for_status() # Raise exception for non-2xx status codes
                except requests.exceptions.RequestException as e:
                    print(f"Home Server failed: {e}. Attempting auto-fallback to Venice AI...")
                    if self.venice_key:
                        wav_buffer.seek(0)
                        response = self.process_venice_request(wav_buffer)
                        print("Fallback to Venice AI successful.")
                    else:
                        raise Exception("Home Server failed and no Venice Key available for fallback.")
                
            elif self.mode == "VENICE":
                # --- VENICE API REQUEST ---
                wav_buffer.seek(0)
                response = self.process_venice_request(wav_buffer)

            # Process Response
            if response and response.status_code == 200:
                result = response.json()
                text = result.get("text", "").strip()
                print(f"[{self.mode}] Heard: {text}")
                
                if text:
                    # Release modifier keys in case they are physically held down
                    kb = pynput_keyboard.Controller()
                    kb.release(pynput_keyboard.Key.ctrl)
                    kb.release(pynput_keyboard.Key.alt)
                    kb.release(pynput_keyboard.Key.shift)
                    time.sleep(0.2) 
                    pyautogui.write(text + " ") 
            else:
                status = response.status_code if response else "Unknown"
                text = response.text if response else "No response"
                print(f"API Error ({self.mode}): {status} - {text}")
                self.update_icon("gray", "API Error")

        except Exception as e:
            print(f"Network Error: {e}")
            self.update_icon("gray", "Net Error")

        self.reset_ui()

    def reset_ui(self):
        disp_name = self.device_name.replace("Microsoft", "").strip()[:10]
        if self.mode == "HOME":
            self.update_icon("green", f"Home Server ({disp_name})")
        elif self.mode == "VENICE":
            self.update_icon("cyan", f"Venice (Road) ({disp_name})")
        else:
            self.update_icon("gray", "Error State")

    def run(self):
        self.icon.run()

if __name__ == "__main__":
    app = SpeechCopilot()
    app.run()
