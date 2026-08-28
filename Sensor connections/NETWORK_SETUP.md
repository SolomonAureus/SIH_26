# BUERLYPH shared Wi-Fi connections

The laptop, phone, and ESP32 must join the same Wi-Fi network.

```text
Phone IP-camera stream ──Wi-Fi──> VITA Python detector ──> BUERLYPH localhost
ESP32 /data endpoint   ──Wi-Fi──────────────────────────> BUERLYPH dashboard
```

`localhost` always means the device on which it is written. The phone cannot send to the laptop by using `localhost`; use the laptop and phone LAN addresses, such as `192.168.1.x`.

## 1. Phone camera

Use a phone camera application that exposes an MJPEG or RTSP stream on the local network. Find the stream URL shown by the application, for example:

```text
http://192.168.1.25:8080/video
```

Test that URL from the laptop first. For direct raw display in the dashboard, set this value at the top of `app.js`:

```js
phoneCameraUrl: 'http://192.168.1.25:8080/video',
```

Reload the page, press **SCAN**, and select **PHONE WIFI CAMERA**. Direct browser display requires an HTTP/MJPEG URL; browsers cannot display RTSP directly.

To run wound localization on the phone stream, pass the URL to VITA and select **VITA RGB INFERENCE** in the dashboard:

```bash
python -m scripts.run_rgb_live \
  --camera 'http://192.168.1.25:8080/video' \
  --samples 100 \
  --sampling-fps 1 \
  --no-wound-timeout 120 \
  --device cpu \
  --no-preview
```

OpenCV must have support for the stream's codec. MJPEG over HTTP is the most broadly compatible option for this prototype.

## 2. ESP32 telemetry

Open `esp32_wifi_telemetry.ino` and set:

```cpp
const char *WIFI_SSID = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
```

The reference sketch assumes:

- DS18B20 temperature sensor on GPIO 4
- Analog moisture sensor on GPIO 34
- MAX30102/MAX30105-compatible SpO2 sensor on I2C SDA 21 / SCL 22

Install the OneWire, DallasTemperature, and SparkFun MAX3010x libraries in the Arduino IDE. Adjust the pins and moisture calibration constants before uploading.

After boot, Serial Monitor prints an address such as:

```text
ESP32 data URL: http://192.168.1.80/data
```

Test it from the laptop. It should return:

```json
{
  "temperature": 36.7,
  "moisture": 61.0,
  "humidity": 61.0,
  "spo2": 98,
  "spo2Valid": true,
  "heartRate": 76,
  "rssi": -51,
  "uptimeMs": 123456
}
```

Then set the endpoint at the top of `app.js`:

```js
sensorHttpUrl: 'http://192.168.1.80/data',
```

The dashboard polls it every two seconds. The three cards and the right-side telemetry table update together. If the endpoint is blank, the dashboard continues using simulated values.

For stable use, reserve the phone and ESP32 addresses in the router so their IP addresses do not change.
