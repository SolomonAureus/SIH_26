#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_ADS1X15.h>
#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

// Sensor Pins
#define ONE_WIRE_BUS 0        // D3
#define TdsSensorPin A0
#define UVC_LED_PIN 15        // D8
#define HEATER_PIN 12         // D6

// Settings
#define VREF 3.3
#define SCOUNT 30

// WiFi AP credentials
const char* ssid = "ESP8266_PureStream";
const char* password = "";

// Initialize objects
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
Adafruit_ADS1115 ads;
ESP8266WebServer server(80);

// Sensor variables
int analogBuffer[SCOUNT];
int analogBufferTemp[SCOUNT];
int analogBufferIndex = 0;
int copyIndex = 0;

float averageVoltage = 0;
float tdsValue = 0;
float turbidityVoltage = 0;
float temperature = 0;
float turbidityNTU = 0;

// State variables
bool uvcState = false;
bool heaterState = false;
bool adsConnected = false; // THE FIX: Flag to track if the sensor is actually alive

// ===== HELPER FUNCTIONS =====

int getMedianNum(int bArray[], int iFilterLen) {
  int bTab[iFilterLen];
  for (byte i = 0; i < iFilterLen; i++) bTab[i] = bArray[i];
  int i, j, bTemp;
  for (j = 0; j < iFilterLen - 1; j++) {
    for (i = 0; i < iFilterLen - j - 1; i++) {
      if (bTab[i] > bTab[i + 1]) {
        bTemp = bTab[i];
        bTab[i] = bTab[i + 1];
        bTab[i + 1] = bTemp;
      }
    }
  }
  if ((iFilterLen & 1) > 0)
    bTemp = bTab[(iFilterLen - 1) / 2];
  else
    bTemp = (bTab[iFilterLen / 2] + bTab[iFilterLen / 2 - 1]) / 2;
  return bTemp;
}

void updateSensorReadings() {
  // Read TDS analog value every 40ms
  static unsigned long analogSampleTimepoint = millis();
  if (millis() - analogSampleTimepoint > 40U) {
    analogSampleTimepoint = millis();
    analogBuffer[analogBufferIndex] = analogRead(TdsSensorPin);
    analogBufferIndex++;
    if (analogBufferIndex == SCOUNT) analogBufferIndex = 0;
  }

  // Calculate TDS and read blocking sensors every 800ms
  static unsigned long printTimepoint = millis();
  if (millis() - printTimepoint > 800U) {
    printTimepoint = millis();

    // Read Temperature
    sensors.requestTemperatures();
    temperature = sensors.getTempCByIndex(0);

    // Calculate TDS
    for (copyIndex = 0; copyIndex < SCOUNT; copyIndex++)
      analogBufferTemp[copyIndex] = analogBuffer[copyIndex];

    averageVoltage = getMedianNum(analogBufferTemp, SCOUNT) * VREF / 1024.0;

    float calcTemp = (temperature == -127.0) ? 25.0 : temperature;
    float compensationCoefficient = 1.0 + 0.02 * (calcTemp - 25.0);
    float compensationVoltage = averageVoltage / compensationCoefficient;

    tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage
                - 255.86 * compensationVoltage * compensationVoltage
                + 857.39 * compensationVoltage) * 0.5;

    // Read Turbidity ONLY if the sensor was found during boot
    if (adsConnected) {
      int16_t adc0 = ads.readADC_SingleEnded(0);
      turbidityVoltage = adc0 * 0.1875 / 1000.0;
      turbidityNTU = (turbidityVoltage < 2.5) ? (2.5 - turbidityVoltage) * 10 : 0;
    } else {
      turbidityNTU = 0; // Fallback value so it doesn't crash
    }

    // Serial Output for Debugging
    if (temperature == -127.0) {
      Serial.println("Temp Error (Check 4.7k resistor)");
    } else {
      Serial.print("Temp: "); Serial.print(temperature, 1);
      Serial.print("C | TDS: "); Serial.print((int)tdsValue);
      Serial.print(" ppm | Turb: "); Serial.print(turbidityNTU);
      Serial.println(" NTU");
    }
  }
}

// ===== WEB SERVER HANDLERS =====

void handleGetData() {
  String json = "{";
  json += "\"temperature\":" + String(temperature, 1) + ",";
  json += "\"tds\":" + String((int)tdsValue) + ",";
  json += "\"turbidity\":" + String(turbidityNTU) + ",";
  json += "\"heaterState\":" + String(heaterState ? "true" : "false") + ",";
  json += "\"uvcState\":" + String(uvcState ? "true" : "false");
  json += "}";
  
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

void handleUVC() {
  if (server.hasArg("state")) {
    String state = server.arg("state");
    if (state == "on") {
      digitalWrite(UVC_LED_PIN, HIGH);
      uvcState = true;
    } else if (state == "off") {
      digitalWrite(UVC_LED_PIN, LOW);
      uvcState = false;
    }
    String response = "{\"uvcState\":" + String(uvcState ? "true" : "false") + "}";
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "application/json", response);
  }
}

void handleHeater() {
  if (server.hasArg("state")) {
    String state = server.arg("state");
    if (state == "on") {
      digitalWrite(HEATER_PIN, HIGH);
      heaterState = true;
    } else if (state == "off") {
      digitalWrite(HEATER_PIN, LOW);
      heaterState = false;
    }
    String response = "{\"heaterState\":" + String(heaterState ? "true" : "false") + "}";
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.send(200, "application/json", response);
  }
}

// ===== SETUP =====

void setup() {
  Serial.begin(9600);
  delay(1000);
  
  sensors.begin();
  
  pinMode(TdsSensorPin, INPUT);
  pinMode(UVC_LED_PIN, OUTPUT);
  pinMode(HEATER_PIN, OUTPUT);
  
  digitalWrite(UVC_LED_PIN, LOW);
  digitalWrite(HEATER_PIN, LOW);

  // Safely check for ADS1115 and set the flag
  if (!ads.begin()) {
    adsConnected = false;
    Serial.println("WARNING: ADS1115 not found. Bypassing.");
  } else {
    adsConnected = true;
    Serial.println("ADS1115 connected.");
  }

  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  
  server.on("/data", HTTP_GET, handleGetData);
  server.on("/uvc", handleUVC);
  server.on("/heater", handleHeater);
  server.begin();
}

// ===== MAIN LOOP =====

void loop() {
  server.handleClient();
  updateSensorReadings();
  yield(); // Keep the ESP8266 background tasks happy
}