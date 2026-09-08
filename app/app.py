import time
import torch
import numpy as np
import sounddevice as sd
from collections import deque
from flask import Flask, jsonify, request, render_template
from df.enhance import init_df, enhance

# --- CONFIGURATION ---
SAMPLE_RATE = 48000
CHUNK_MS = 300
OVERLAP_MS = 10
STEP_MS = CHUNK_MS - OVERLAP_MS

CHUNK_SAMPLES = int(SAMPLE_RATE * (CHUNK_MS / 1000.0))
OVERLAP_SAMPLES = int(SAMPLE_RATE * (OVERLAP_MS / 1000.0))
STEP_SAMPLES = int(SAMPLE_RATE * (STEP_MS / 1000.0))

print("Loading Tactical AI Weights...")
model, df_state, _ = init_df()

# Fix: Keep crossfade tensors on the CPU (Matches Jupyter Notebook exactly)
fade_out = torch.linspace(1.0, 0.0, OVERLAP_SAMPLES)
fade_in = torch.linspace(0.0, 1.0, OVERLAP_SAMPLES)
prev_overlap = torch.zeros(1, OVERLAP_SAMPLES)

# --- ROLLING BUFFERS ---
MAX_BUFFER = SAMPLE_RATE * 1  # 1 second of audio memory
buffer_mic1 = deque([0.0]*MAX_BUFFER, maxlen=MAX_BUFFER)
buffer_mic2 = deque([0.0]*MAX_BUFFER, maxlen=MAX_BUFFER)
buffer_out = deque([0.0]*MAX_BUFFER, maxlen=MAX_BUFFER)

app_state = {"denoise_enabled": True}

# --- AUDIO CALLBACK ---
def audio_callback(indata, outdata, frames, time_info, status):
    global prev_overlap
    
    mic1_raw = indata[:, 0]  # XLR Mic
    mic2_raw = indata[:, 1]  # 1/4" Mic
    
    buffer_mic1.extend(mic1_raw.tolist())
    buffer_mic2.extend(mic2_raw.tolist())

    if app_state["denoise_enabled"]:
        # Fix: Keep incoming tensor on CPU. DeepFilterNet handles GPU transfers internally.
        incoming_tensor = torch.from_numpy(mic1_raw).float().unsqueeze(0)
        full_chunk = torch.cat([prev_overlap, incoming_tensor], dim=-1)
        
        with torch.no_grad():
            cleaned = enhance(model, df_state, full_chunk)
            
        cleaned[:, :OVERLAP_SAMPLES] *= fade_in
        overlap_faded = prev_overlap * fade_out
        cleaned[:, :OVERLAP_SAMPLES] += overlap_faded
        
        prev_overlap = cleaned[:, -OVERLAP_SAMPLES:].clone()
        
        # Fix: Removed .cpu() since it never left the CPU
        out_audio = cleaned[:, :STEP_SAMPLES].squeeze(0).numpy()
    else:
        out_audio = mic1_raw.copy()
        prev_overlap = torch.zeros(1, OVERLAP_SAMPLES)

    outdata[:, 0] = out_audio
    outdata[:, 1] = out_audio
    buffer_out.extend(out_audio.tolist())

# --- FLASK SERVER ---
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/toggle", methods=["POST"])
def toggle():
    app_state["denoise_enabled"] = request.json.get("enabled", True)
    return jsonify({"status": "success", "state": app_state["denoise_enabled"]})

@app.route("/api/data", methods=["GET"])
def get_20_ms_data():
    view_samples = int(SAMPLE_RATE * (20 / 1000.0))
    downsample = 32
    
    m1 = np.array(list(buffer_mic1)[-view_samples:])
    m2 = np.array(list(buffer_mic2)[-view_samples:])
    out = np.array(list(buffer_out)[-view_samples:])
    
    step = max(1, len(m1) // downsample)
    
    return jsonify({
        "mic1": m1[::step].round(4).tolist(),
        "mic2": m2[::step].round(4).tolist(),
        "output": out[::step].round(4).tolist()
    })

if __name__ == "__main__":
    stream = sd.Stream(channels=(2, 2), samplerate=SAMPLE_RATE, blocksize=STEP_SAMPLES, dtype='float32', callback=audio_callback)
    stream.start()
    app.run(host="0.0.0.0", port=5000, use_reloader=False, threaded=True, debug=True)