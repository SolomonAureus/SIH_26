# BUERLYPH sensor dashboard

A local-first, retro pixel dashboard for ESP32 wound-monitoring data. It includes:

- Live temperature and humidity readouts
- Central multi-source visual scanner with camera discovery and an animated demo view
- Visible, ultraviolet, infrared, and thermal-map display modes
- Healing progress status against the expected curve
- A slide-out screen switcher
- Observed vs. expected trend graphs for healing, temperature, and humidity
- Responsive desktop/mobile layout

## Run locally

No build step is required. From this directory, run:

```bash
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

## Connect an ESP32

Edit `CONFIG` at the top of `app.js`:

```js
const CONFIG = {
  websocketUrl: 'ws://192.168.1.80/ws',
  cameraStreamUrl: 'http://192.168.1.80:81/stream',
  cameraSources: [
    { id: 'uv-cam', label: 'UV CAMERA', type: 'mjpeg', url: 'http://192.168.1.81/stream', spectrum: 'ultraviolet' },
    { id: 'ir-cam', label: 'IR CAMERA', type: 'mjpeg', url: 'http://192.168.1.82/stream', spectrum: 'infrared' },
  ],
};
```

The dashboard expects WebSocket messages shaped like:

```json
{
  "temperature": 36.7,
  "humidity": 61,
  "healing": 68
}
```

The ESP32-CAM and configured sensor streams should expose an MJPEG endpoint. USB cameras—including browser-compatible UV and infrared devices—are detected with the **SCAN** button in the visual scanner. Camera access works on `localhost` or HTTPS and requires browser permission.

The visual mode menu provides display transformations for visible, ultraviolet, infrared, and thermal-map presentations. It does not convert a normal webcam into a true UV, infrared, or thermal sensor; accurate spectral data still requires the corresponding hardware.

When the endpoints are blank, the dashboard remains fully interactive and uses simulated live readings and a procedural camera placeholder.

## Show VITA wound detection in BUERLYPH

Run the dashboard server from the project directory in terminal 1:

```bash
python3 -m http.server 8080
```

Run the RGB detector in terminal 2 using the same Python environment in which the model dependencies are installed:

```bash
python -m scripts.run_rgb_live \
  --camera 0 \
  --samples 10 \
  --sampling-fps 1 \
  --no-wound-timeout 120 \
  --device cpu \
  --no-preview
```

Open `http://localhost:8080`, then choose **VITA RGB INFERENCE** from the **INPUT SOURCE** menu. The central scanner shows a fluid camera preview while the **LAST MODEL FRAME** inset updates whenever the CPU finishes wound segmentation. The bar above it reports the model status, wound area, confidence, normalized red ratio, and accepted sample count.

Python owns the camera while VITA inference is selected. Do not also select the same physical webcam through the browser camera options. Each run ends after the requested number of accepted samples; the last result remains visible in the dashboard. The pipeline also saves the final aggregate assessment under `outputs/rgb_assessment_*.json`.

The live integration uses three replace-on-update files served by the local web server:

- `outputs/live_camera.jpg` — fast unannotated camera preview
- `outputs/live_preview.jpg` — latest annotated detector frame
- `outputs/live_status.json` — latest quality, segmentation, RGB, and progress values

These are runtime files and are intentionally not committed to Git.
