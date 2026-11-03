# Firmware

Arduino sketch for the NodeMCU ESP8266 node: `IoT_Weather_Station.ino`.

Before uploading to the board, fill in your own values at the top of the sketch:
Wi-Fi name and password, Blynk template ID and auth token, ThingSpeak write API key.

Libraries used: ESP8266WiFi, BlynkSimpleEsp8266 (Blynk), Wire, LiquidCrystal_I2C, DHT (Adafruit), Adafruit BMP280 Library (Adafruit_BMP280).

Timers: DHT22 2 s, pressure sensor 3 s, rain sensor 0.5 s, LCD 2 s, ThingSpeak upload 15 min.

ThingSpeak fields: 1 DHT22 temperature, 2 DHT22 humidity, 3 pressure-sensor die temperature, 4 station pressure, 5 rain status.

Photos and wiring diagram are in `../images/`.
