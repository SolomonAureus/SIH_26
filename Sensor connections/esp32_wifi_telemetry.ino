/*
  BUERLYPH ESP32 Wi-Fi telemetry node

  Hardware assumed by this reference:
    - DS18B20 temperature sensor on GPIO 4 (4.7k pull-up required)
    - Analog moisture sensor on GPIO 34
    - MAX30102/MAX30105-compatible SpO2 board on I2C (SDA 21, SCL 22)

  The ESP32 joins the same router as the dashboard and serves:
    GET /data   -> temperature, moisture and SpO2 JSON
    GET /health -> link/sensor status JSON

  Required Arduino libraries:
    - OneWire
    - DallasTemperature
    - SparkFun MAX3010x Pulse and Proximity Sensor Library
*/

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

// ---------- Change these values for your network and wiring ----------
const char *WIFI_SSID = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

constexpr uint8_t ONE_WIRE_PIN = 4;
constexpr uint8_t MOISTURE_PIN = 34;
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;

// Calibrate these using raw readings from your own moisture probe.
constexpr int MOISTURE_DRY_RAW = 3000;
constexpr int MOISTURE_WET_RAW = 1200;
constexpr unsigned long SENSOR_INTERVAL_MS = 2000;
// ---------------------------------------------------------------------

WebServer server(80);
OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature temperatureSensor(&oneWire);
MAX30105 pulseOximeter;

float temperatureC = NAN;
float moisturePercent = NAN;
int32_t spo2Percent = 0;
int32_t heartRate = 0;
int8_t spo2Valid = 0;
int8_t heartRateValid = 0;
bool pulseSensorConnected = false;

uint32_t irBuffer[100];
uint32_t redBuffer[100];
uint16_t pulseSampleCount = 0;
uint8_t samplesSinceCalculation = 0;
unsigned long lastSlowSensorRead = 0;
unsigned long lastWifiAttempt = 0;

float clampPercent(float value) {
  if (value < 0.0f) return 0.0f;
  if (value > 100.0f) return 100.0f;
  return value;
}

void addCommonHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
  server.sendHeader("Access-Control-Allow-Private-Network", "true");
  server.sendHeader("Cache-Control", "no-store");
}

String jsonNumberOrNull(float value, uint8_t decimals) {
  return isnan(value) ? "null" : String(value, decimals);
}

void handleData() {
  String json = "{";
  json += "\"temperature\":" + jsonNumberOrNull(temperatureC, 1) + ",";
  json += "\"moisture\":" + jsonNumberOrNull(moisturePercent, 1) + ",";
  json += "\"humidity\":" + jsonNumberOrNull(moisturePercent, 1) + ",";
  json += "\"spo2\":";
  json += spo2Valid ? String(spo2Percent) : String("null");
  json += ",";
  json += "\"spo2Valid\":" + String(spo2Valid ? "true" : "false") + ",";
  json += "\"heartRate\":";
  json += heartRateValid ? String(heartRate) : String("null");
  json += ",";
  json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"uptimeMs\":" + String(millis());
  json += "}";
  addCommonHeaders();
  server.send(200, "application/json", json);
}

void handleHealth() {
  String json = "{";
  json += "\"wifi\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"pulseSensor\":" + String(pulseSensorConnected ? "true" : "false") + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";
  addCommonHeaders();
  server.send(200, "application/json", json);
}

void handleOptions() {
  addCommonHeaders();
  server.send(204, "text/plain", "");
}

void updateTemperatureAndMoisture() {
  if (millis() - lastSlowSensorRead < SENSOR_INTERVAL_MS) return;
  lastSlowSensorRead = millis();

  temperatureSensor.requestTemperatures();
  const float reading = temperatureSensor.getTempCByIndex(0);
  temperatureC = reading == DEVICE_DISCONNECTED_C ? NAN : reading;

  const int rawMoisture = analogRead(MOISTURE_PIN);
  const float span = float(MOISTURE_DRY_RAW - MOISTURE_WET_RAW);
  moisturePercent = span == 0.0f
    ? NAN
    : clampPercent((MOISTURE_DRY_RAW - rawMoisture) * 100.0f / span);
}

void updatePulseOximeter() {
  if (!pulseSensorConnected) return;
  pulseOximeter.check();

  while (pulseOximeter.available()) {
    const uint32_t red = pulseOximeter.getRed();
    const uint32_t ir = pulseOximeter.getIR();
    pulseOximeter.nextSample();

    if (pulseSampleCount < 100) {
      redBuffer[pulseSampleCount] = red;
      irBuffer[pulseSampleCount] = ir;
      pulseSampleCount++;
    } else {
      for (uint16_t i = 1; i < 100; i++) {
        redBuffer[i - 1] = redBuffer[i];
        irBuffer[i - 1] = irBuffer[i];
      }
      redBuffer[99] = red;
      irBuffer[99] = ir;
      samplesSinceCalculation++;
    }

    if (pulseSampleCount == 100 && samplesSinceCalculation >= 25) {
      maxim_heart_rate_and_oxygen_saturation(
        irBuffer, 100, redBuffer,
        &spo2Percent, &spo2Valid, &heartRate, &heartRateValid
      );
      samplesSinceCalculation = 0;
    }
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  const unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("ESP32 data URL: http://");
    Serial.print(WiFi.localIP());
    Serial.println("/data");
  } else {
    Serial.println("Wi-Fi connection timed out; retrying in loop.");
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  temperatureSensor.begin();
  temperatureSensor.setResolution(9);

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  pulseSensorConnected = pulseOximeter.begin(Wire, I2C_SPEED_FAST);
  if (pulseSensorConnected) {
    // brightness, averaging, LED mode, sample rate, pulse width, ADC range
    pulseOximeter.setup(60, 4, 2, 100, 411, 4096);
  } else {
    Serial.println("WARNING: MAX30102/MAX30105 not found; SpO2 will be null.");
  }

  connectWifi();
  server.on("/data", HTTP_GET, handleData);
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/data", HTTP_OPTIONS, handleOptions);
  server.onNotFound([]() {
    addCommonHeaders();
    server.send(404, "application/json", "{\"error\":\"not found\"}");
  });
  server.begin();
}

void loop() {
  server.handleClient();
  updatePulseOximeter();
  updateTemperatureAndMoisture();

  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiAttempt > 10000) {
    lastWifiAttempt = millis();
    WiFi.reconnect();
  }
  delay(1);
}
