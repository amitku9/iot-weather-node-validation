

// BLYNK CONFIGURATION 

#define BLYNK_TEMPLATE_ID   "YOUR_TEMPLATE_ID"
#define BLYNK_TEMPLATE_NAME "WEATHER MONITORING SYSTEM"
#define BLYNK_AUTH_TOKEN    "YOUR_BLYNK_AUTH_TOKEN"
#define BLYNK_PRINT Serial


// LIBRARY INCLUDES

#include <ESP8266WiFi.h>          // Wi-Fi connectivity for NodeMCU ESP8266
#include <BlynkSimpleEsp8266.h>   // Blynk IoT platform client
#include <Wire.h>                 // I2C communication (BMP280 + LCD)
#include <LiquidCrystal_I2C.h>   // 20x4 I2C LCD driver
#include <DHT.h>                  // DHT22 sensor library (Adafruit)
#include <Adafruit_BMP280.h>      // BMP280 pressure sensor


// WI-FI CREDENTIALS

char ssid[] = "YOUR_WIFI_NAME";
char pass[] = "YOUR_WIFI_PASSWORD";


// THINGSPEAK CONFIGURATION
// Field assignments:
//   field1 = DHT22 ambient temperature (°C)
//   field2 = DHT22 relative humidity (%)
//   field3 = BMP280 internal die temperature (°C) — pressure compensation ref
//   field4 = BMP280 station-level pressure (hPa)
//   field5 = MH-RD rain status (1=rain, 0=dry)

const char* TS_SERVER  = "api.thingspeak.com";
const char* TS_API_KEY = "YOUR_THINGSPEAK_WRITE_KEY";
WiFiClient tsClient;


// DHT22 CONFIGURATION

#define DHTPIN   D3      // DHT22 data pin — NodeMCU D3 (GPIO0)
#define DHTTYPE  DHT22   // Sensor type: DHT22 (AM2302)
DHT dht(DHTPIN, DHTTYPE);


// BMP280 SENSOR OBJECT

Adafruit_BMP280 bmp;


// 20x4 I2C LCD CONFIGURATION
// PCF8574 I2C backpack at address 0x27, 20 columns, 4 rows

LiquidCrystal_I2C lcd(0x27, 20, 4);


// RAIN SENSOR CONFIGURATION

const int RAIN_PIN = D5;    // MH-RD DOUT to NodeMCU D5 (GPIO14)


// TEMPERATURE ALERT THRESHOLDS
// FR-11: Alert above HIGH_TEMP_THRESHOLD
// FR-12: Alert below LOW_TEMP_THRESHOLD

const float HIGH_TEMP_THRESHOLD = 38.0;   // °C — alert if exceeded
const float LOW_TEMP_THRESHOLD  = 10.0;   // °C — alert if below


// GLOBAL SENSOR STATE VARIABLES
// Updated by sensor read functions; read by uploadToThingSpeak() and LCD

float    currentTemperature = NAN;    // DHT22 ambient temperature (°C)
float    currentHumidity    = NAN;    // DHT22 relative humidity (%)
float    currentPressure    = 0.0;    // BMP280 station-level pressure (hPa)
bool     currentRainStatus  = false;  // true = rain detected, false = dry
bool     dht_error          = true;   // true = DHT22 last read failed
bool     bmp_error          = true;   // true = BMP280 last read failed


// RAIN EVENT TIMING VARIABLES

bool          isRaining        = false;
unsigned long rainStartTime    = 0;
unsigned long lastRainDuration = 0;


// BLYNK TIMER — non-blocking cooperative scheduler

BlynkTimer timer;


// SETUP FUNCTION

void setup() {
  Serial.begin(115200);
  Serial.println(F("IoT Weather Station - Amit Kumar"));

  // Initialise 20x4 LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("IoT Weather Station");
  lcd.setCursor(0, 1); lcd.print("M.C. JAIPUR");
  lcd.setCursor(0, 2); lcd.print("Initialising...");
  delay(2000);

  // Initialise DHT22 sensor
  // BUG-01 fix: 2-second warm-up delay required after power-on per datasheet
  dht.begin();
  delay(2000);
  Serial.println(F("DHT22 initialised"));

  // Initialise BMP280 pressure sensor
  // I2C address 0x76 (SDO pin tied LOW on this module)
  if (!bmp.begin(0x76)) {
    Serial.println(F("BMP280 not found at 0x76! Check I2C wiring and address"));
    bmp_error = true;
  } else {
    Serial.println(F("BMP280 initialised successfully"));
    bmp_error = false;
  }

  // Configure rain sensor digital input pin
  pinMode(RAIN_PIN, INPUT);
  Serial.println(F("Rain sensor pin configured"));

  // Connect to Wi-Fi and Blynk server
  Blynk.begin(BLYNK_AUTH_TOKEN, ssid, pass);
  Serial.println(F("Blynk connection initiated"));

  // Schedule all sensor tasks via BlynkTimer (non-blocking — no delay() in loop)
  timer.setInterval(2000L,   readDHTSensor);       // DHT22 every 2 s (datasheet minimum)
  timer.setInterval(500L,    readRainSensor);      // Rain sensor every 500 ms
  timer.setInterval(3000L,   readPressureSensor);  // BMP280 every 3 s
  timer.setInterval(2000L,   updateLCDDisplay);    // LCD refresh every 2 s (NFR-02)
  timer.setInterval(900000L, uploadToThingSpeak);  // ThingSpeak every 15 min (BUG-04 fix)

  Serial.println(F("Setup complete. Entering monitoring loop."));
}


// DHT22 TEMPERATURE AND HUMIDITY READING
// Called by BlynkTimer every 2000 ms
// Input:  none (reads directly from DHT22 on DHTPIN)
// Output: updates currentTemperature, currentHumidity, dht_error
//         writes to Blynk virtual pins V0 (temperature) and V1 (humidity)
// BUG-03 fix: isnan() validation rejects invalid sensor readings

void readDHTSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();   // Celsius by default

  if (isnan(h) || isnan(t)) {
    // NaN indicates sensor read failure (timeout or wire fault)
    Serial.println(F("DHT22 read failed - NaN returned"));
    dht_error = true;
    return;   // Exit: do not update globals or transmit
  }

  // Valid reading — update global state and transmit to Blynk
  currentHumidity    = h;
  currentTemperature = t;
  dht_error = false;

  Blynk.virtualWrite(V0, t);   // V0 = DHT22 ambient temperature
  Blynk.virtualWrite(V1, h);   // V1 = DHT22 relative humidity

  Serial.print(F("DHT22 - T: ")); Serial.print(t);
  Serial.print(F(" C  H: ")); Serial.print(h); Serial.println(F(" %"));
}


// BMP280 PRESSURE READING
// Called by BlynkTimer every 3000 ms
// Input:  none (reads via I2C from BMP280 at address 0x76)
// Output: updates currentPressure, bmp_error
//         writes to Blynk virtual pin V3 (station-level pressure)
// Validation: physical range gate 50000–110000 Pa (500–1100 hPa)

void readPressureSensor() {
  float p_pa = bmp.readPressure();   // Returns station-level pressure in Pascals

  // Validate: physically plausible range for Jaipur (~411 m AMSL)
  // Expected station pressure: approx 95000 to 100000 Pa under normal conditions
  if (p_pa < 50000 || p_pa > 110000) {
    Serial.println(F("BMP280 read failed - out of valid range"));
    bmp_error = true;
    return;
  }

  currentPressure = p_pa / 100.0;   // Convert Pascals to hectopascals (hPa)
  bmp_error = false;

  Blynk.virtualWrite(V3, currentPressure);   // V3 = station-level pressure
  Serial.print(F("BMP280 - P: ")); Serial.print(currentPressure);
  Serial.println(F(" hPa"));
}


// THINGSPEAK UPLOAD SCHEDULER
// Called by BlynkTimer every 900000 ms (15 minutes) — BUG-04 fix
// Input:  current global sensor state variables
// Output: calls sendToThingSpeak() with validated readings
// BUG-04: decoupled from readPressureSensor() to respect ThingSpeak
//         free-tier 15-second minimum update interval and to align
//         uploads with the 3-hourly IMD synoptic schedule

void uploadToThingSpeak() {
  if (dht_error || bmp_error) {
    Serial.println(F("Skipping ThingSpeak upload: sensor error state"));
    return;
  }
  float bmp_temp = bmp.readTemperature();   // BMP280 internal die temperature
  sendToThingSpeak(currentTemperature, currentHumidity,
                   bmp_temp, currentPressure, currentRainStatus);
}


// RAIN SENSOR READING
// Called by BlynkTimer every 500 ms
// Input:  digital read from RAIN_PIN (D5/GPIO14)
// Output: updates currentRainStatus, isRaining, rainStartTime, lastRainDuration
//         writes to Blynk virtual pin V2 (rain status binary)
// BUG-05 fix: secondary confirmation logic prevents false positives
//   from condensation at very high humidity (>= 98% RH)
//   Rain is confirmed only if: humidity < 98% OR LOW persists >= 2 polls

void readRainSensor() {
  static int lowCount = 0;
  int state = digitalRead(RAIN_PIN);
  bool rawWet = (state == LOW);   // LOW = rain detected (active LOW sensor)

  // Count consecutive LOW readings for persistence check
  if (rawWet) { lowCount++; } else { lowCount = 0; }

  // BUG-05 fix: confirm rain only if not in condensation-humidity range,
  // or if the LOW signal has persisted for >= 2 consecutive 500 ms polls
  bool confirmedWet = rawWet && (currentHumidity < 98.0 || lowCount >= 2);
  currentRainStatus = confirmedWet;

  // Track rain event timing
  if (currentRainStatus && !isRaining) {
    isRaining     = true;
    rainStartTime = millis();
    Serial.println(F("Rain event started."));
  } else if (!currentRainStatus && isRaining) {
    isRaining        = false;
    lastRainDuration = millis() - rainStartTime;
    Serial.print(F("Rain stopped. Duration: "));
    Serial.print(lastRainDuration / 1000); Serial.println(F(" s"));
  }

  Blynk.virtualWrite(V2, currentRainStatus ? 1 : 0);   // V2 = rain status
}


// THINGSPEAK DATA TRANSMISSION
// Called by uploadToThingSpeak() every 15 minutes
// Input:  t_dht (DHT22 temp °C), hum (humidity %), t_bmp (BMP die temp °C),
//         pres (pressure hPa), rain (bool rain status)
// Output: HTTP GET request to ThingSpeak REST API; logs response to Serial
// Guard:  Blynk.connected() check ensures Wi-Fi is available before attempting

void sendToThingSpeak(float t_dht, float hum, float t_bmp,
                       float pres, bool rain) {
  if (!Blynk.connected()) {
    Serial.println(F("Wi-Fi not connected - skipping ThingSpeak upload"));
    return;
  }

  if (tsClient.connect(TS_SERVER, 80)) {
    // Build HTTP GET request string
    String req = "GET /update?api_key=" + String(TS_API_KEY);
    if (!isnan(t_dht)) req += "&field1=" + String(t_dht, 2);
    if (!isnan(hum))   req += "&field2=" + String(hum, 2);
    req += "&field3=" + String(t_bmp, 2);
    req += "&field4=" + String(pres, 2);             // Station-level pressure
    req += "&field5=" + String(rain ? 1 : 0);
    req += " HTTP/1.1\r\nHost: " + String(TS_SERVER);
    req += "\r\nConnection: close\r\n\r\n";

    tsClient.print(req);

    // Read and log HTTP response code
    unsigned long timeout = millis();
    while (tsClient.available() == 0) {
      if (millis() - timeout > 5000) {
        Serial.println(F("ThingSpeak: response timeout."));
        tsClient.stop();
        return;
      }
    }
    while (tsClient.available()) {
      String line = tsClient.readStringUntil('\r');
      Serial.print(F("TS response: ")); Serial.println(line);
      break;   // Log first response line only (HTTP status code)
    }
    tsClient.stop();
  } else {
    Serial.println(F("ThingSpeak: connection failed."));
  }
}


// LCD DISPLAY UPDATE AND ALERT FUNCTION
// Called by BlynkTimer every 2000 ms
// Input:  current global sensor state variables
// Output: updates all 4 LCD rows; triggers Blynk.logEvent() on threshold breach
// Row layout:
//   Row 0: Station identifier (fixed)
//   Row 1: Temperature (°C) and Humidity (%)
//   Row 2: Pressure (hPa) and Rain status (X=rain, O=dry)
//   Row 3: Dynamic — error message / threshold warning / last rain duration / OK

void updateLCDDisplay() {
  lcd.clear();

  // Row 0: Station identifier
  lcd.setCursor(0, 0);
  lcd.print("M.C. JAIPUR");

  // Row 1: Temperature and Humidity
  lcd.setCursor(0, 1);
  if (!dht_error && !isnan(currentTemperature)) {
    lcd.print("T:"); lcd.print(currentTemperature, 1);
    lcd.print("C H:"); lcd.print(currentHumidity, 0); lcd.print("%");
  } else {
    lcd.print("T:--- H:---");
  }

  // Row 2: Station-level pressure and rain status
  lcd.setCursor(0, 2);
  if (!bmp_error && currentPressure != 0.0) {
    lcd.print("P:"); lcd.print(currentPressure, 0);
    lcd.print("hPa Ri:");
    lcd.print(currentRainStatus ? "X" : "O");   // X = rain, O = dry
  } else {
    lcd.print("P:--- Ri:-");
  }

  // Row 3: Dynamic status, warnings, or error messages
  lcd.setCursor(0, 3);
  if (dht_error) {
    lcd.print("DHT Error! Chk wire");
  } else if (bmp_error) {
    lcd.print("BMP Error! Chk wire");
  } else if (!isnan(currentTemperature) &&
             currentTemperature > HIGH_TEMP_THRESHOLD) {
    // FR-11: High temperature threshold alert (>= 38°C)
    lcd.print("WARNING: High Temp!");
    Blynk.logEvent("high_temp", "High temperature alert!");
  } else if (!isnan(currentTemperature) &&
             currentTemperature < LOW_TEMP_THRESHOLD) {
    // FR-12: Low temperature threshold alert (<= 10°C)
    lcd.print("WARNING: Low Temp! ");
    Blynk.logEvent("low_temp", "Low temperature alert!");
  } else if (lastRainDuration > 0 && !isRaining) {
    // Display most recent rain event duration
    unsigned long mins = (lastRainDuration / 1000) / 60;
    unsigned long secs = (lastRainDuration / 1000) % 60;
    lcd.print("Rain: "); lcd.print(mins); lcd.print("m");
    lcd.print(secs); lcd.print("s");
  } else {
    lcd.print("All systems normal.");
  }
}


// MAIN LOOP
// Delegates all work to Blynk (connection management + virtual pin handling)
// and BlynkTimer (scheduled sensor functions).
// No blocking delay() calls — non-blocking cooperative architecture.

void loop() {
  Blynk.run();   // Handles Blynk TCP/IP communication and reconnection
  timer.run();   // Executes all scheduled sensor reading functions
}
