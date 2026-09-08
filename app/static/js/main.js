// Each 20ms update brings 32 points. We want to show 1000ms total.
// 50 updates/sec * 32 points = 1600 total points in the sliding window.
const MAX_POINTS = 1600; 

// Initialize rolling arrays with zeros
let bufferMic1 = new Array(MAX_POINTS).fill(0);
let bufferMic2 = new Array(MAX_POINTS).fill(0);
let bufferOut = new Array(MAX_POINTS).fill(0);

// Canvas setup
const ctxMic1 = document.getElementById('canvas-mic1').getContext('2d');
const ctxMic2 = document.getElementById('canvas-mic2').getContext('2d');
const ctxOut = document.getElementById('canvas-out').getContext('2d');

function resizeCanvas(ctx) {
    ctx.canvas.width = ctx.canvas.clientWidth;
    ctx.canvas.height = ctx.canvas.clientHeight;
}
resizeCanvas(ctxMic1); resizeCanvas(ctxMic2); resizeCanvas(ctxOut);
window.addEventListener('resize', () => {
    resizeCanvas(ctxMic1); resizeCanvas(ctxMic2); resizeCanvas(ctxOut);
});

// Data Polling Loop (Every 20ms)
setInterval(async () => {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        
        // Shift old data out, push new 32 points in
        for(let i = 0; i < data.mic1.length; i++) {
            bufferMic1.shift(); bufferMic1.push(data.mic1[i]);
            bufferMic2.shift(); bufferMic2.push(data.mic2[i]);
            bufferOut.shift(); bufferOut.push(data.output[i]);
        }
    } catch (err) {
        // Silently catch network errors if backend is rebooting
    }
}, 20);

// Rendering Loop (Runs at monitor refresh rate, usually 60fps)
function drawWaveform(ctx, buffer, color) {
    const width = ctx.canvas.width;
    const height = ctx.canvas.height;
    const midY = height / 2;
    
    ctx.clearRect(0, 0, width, height);
    
    // Draw center baseline
    ctx.strokeStyle = '#1f2833';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(width, midY);
    ctx.stroke();
    
    // Draw audio waveform
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    
    const step = width / MAX_POINTS;
    
    for(let i = 0; i < MAX_POINTS; i++) {
        const x = i * step;
        // Audio values are approx -1.0 to 1.0. 
        // We multiply by midY * 0.9 to scale them visually without clipping the canvas edges.
        const y = midY - (buffer[i] * midY * 0.9);
        
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
}

function animate() {
    drawWaveform(ctxMic1, bufferMic1, '#66fcf1'); // Cyan
    drawWaveform(ctxMic2, bufferMic2, '#e23b3b'); // Red
    drawWaveform(ctxOut, bufferOut, '#4caf50');   // Green
    requestAnimationFrame(animate);
}
animate();

// Toggle Button Logic
let isDenoising = true;
const toggleBtn = document.getElementById('toggle-btn');

toggleBtn.addEventListener('click', async () => {
    isDenoising = !isDenoising;
    
    // Update UI instantly
    toggleBtn.innerText = isDenoising ? "AI DENOISER: ON" : "AI DENOISER: OFF";
    toggleBtn.className = isDenoising ? "btn-on" : "btn-off";
    
    // Send state to backend
    await fetch('/api/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: isDenoising })
    });
});