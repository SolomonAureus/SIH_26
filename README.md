# BUERLYPH sensor dashboard

A local-first, retro pixel dashboard for ESP32 wound-monitoring data. It includes:

- Live temperature, moisture, and SpO2 readouts
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
  "moisture": 61,
  "spo2": 98,
  "healing": 68
}
```

The ESP32-CAM and configured sensor streams should expose an MJPEG endpoint. USB cameras—including browser-compatible UV and infrared devices—are detected with the **SCAN** button in the visual scanner. Camera access works on `localhost` or HTTPS and requires browser permission.

The visual mode menu provides display transformations for visible, ultraviolet, infrared, and thermal-map presentations. It does not convert a normal webcam into a true UV, infrared, or thermal sensor; accurate spectral data still requires the corresponding hardware.

When the endpoints are blank, the dashboard remains fully interactive and uses simulated live readings and a procedural camera placeholder.
