#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h> // Handles secure TLS connection to AWS IoT Core
#include <PubSubClient.h>     // MQTT Client for publishing to AWS
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT11.h>
#include <time.h>

// ==========================================
// 1. WI-FI & CLOUD CONFIGURATION
// ==========================================
const char* ssid = "REMAC";
const char* password = "12345678";

// AWS IoT Core Settings
const char* aws_endpoint = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com";
const int aws_port = 8883;
const char* aws_topic = "remac/node1/data";
const char* client_id = "Remac-Node-1";

// Local Dashboard Settings (Update this to your PC's IP address!)
const String local_server_ip = "192.168.43.150"; // <-- Change to your PC's IP from ipconfig
const int local_server_port = 3000;
const int UNIT_ID = 1;

// ==========================================
// 2. AWS SECURITY CERTIFICATES (PEM format)
// ==========================================

// Amazon Root CA 1
const char AWS_CERT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDQTCCAimgAwIBAgITBmyfz5m/jAo54vB4ikPmljZbyjANBgkqhkiG9w0BAQsF
ADA5MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRkwFwYDVQQDExBBbWF6
b24gUm9vdCBDQSAxMB4XDTE1MDUyNjAwMDAwMFoXDTM4MDExNzAwMDAwMFowOTEL
MAkGA1UEBhMCVVMxDzANBgNVBAoTBkFtYXpvbjEZMBcGA1UEAxMQQW1hem9uIFJv
b3QgQ0EgMTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALJ4gHHKeNXj
ca9HgFB0fW7Y14h29Jlo91ghYPl0hAEvrAIthtOgQ3pOsqTQNroBvo3bSMgHFzZM
9O6II8c+6zf1tRn4SWiw3te5djgdYZ6k/oI2peVKVuRF4fn9tBb6dNqcmzU5L/qw
IFAGbHrQgLKm+a/sRxmPUDgH3KKHOVj4utWp+UhnMJbulHheb4mjUcAwhmahRWa6
VOujw5H5SNz/0egwLX0tdHA114gk957EWW67c4cX8jJGKLhD+rcdqsq08p8kDi1L
93FcXmn/6pUCyziKrlA4b9v7LWIbxcceVOF34GfID5yHI9Y/QCB/IIDEgEw+OyQm
jgSubJrIqg0CAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMC
AYYWHQYDVR0OBBYEFIQYzIU07LwMlJQuCFmcx7IQTgoIMA0GCSqGSIb3DQEBCwUA
A4IBAQCY8jdaQZChGsV2USggNiMOruYou6r4lK5IpDB/G/wkjUu0yKGX9rbxenDI
U5PMCCjjmCXPI6T53iHTfIUJrU6adTrCC2qJeHZERxhlbI1Bjjt/msv0tadQ1wUs
N+gDS63pYaACbvXy8MWy7Vu33PqUXHeeE6V/Uq2V8viTO96LXFvKWlJbYK8U90vv
o/ufQJVtMVT8QtPHRh8jrdkPSHCa2XV4cdFyQzR1bldZwgJcJmApzyMZFo6IQ6XU
5MsI+yMRQ+hDKXJioaldXgjUkK642M4UwtBV8ob2xJNDd2ZhwLnoQdeXeGADbkpy
rqXRfboQnoZsG4q5WTP468SQvvG5
-----END CERTIFICATE-----
)EOF";

// Client Certificate
const char AWS_CERT_CRT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDWTCCAkGgAwIBAgIUUAyAqjAsJp1rfWjO270c3bQ7NewwDQYJKoZIhvcNAQEL
BQAwTTFLMEkGA1UECwxCQW1hem9uIFdlYiBTZXJ2aWNlcyBPPUFtYXpvbi5jb20g
SW5jLiBMPVNlYXR0bGUgU1Q9V2FzaGluZ3RvbiBDPVVTMB4XDTI2MDYyODExMTYy
MVoXDTQ5MTIzMTIzNTk1OVowHjEcMBoGA1UEAwwTQVdTIElvVCBDZXJ0aWZpY2F0
ZTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANn3QKOnBY5VGlqVeqK1
BrFA8x22TtvHtm6GsYUo11pPC/ca53IQOHIX1fMfBwE2C6D3kXdoOPANvamF/lVl
V9TnR2hnrH/n2XnFIv+/WK6ajzMp4oEOvRXbGd+L5L5qUkEwP9SAmRkeu7VzC6Te
TqR0lqzlQrfwyxaNcN1Bf767uSlQedz3yaZnFJdOOM3gXN28F00mADs/JLDzfvpz
4+XUR2u2InPZsDJdfBEe0b+qrP7TW7kNzEgZBOlh8MmcRNyqaGs8ZsY07rEMKJP3
XhU9AxAZ9lnEdngzOUsgxn7BRMLT0lbMuSA9+an1nD3rlkSm0EHzy3R1gqXHQMSU
daMCAwEAAaNgMF4wHwYDVR0jBBgwFoAUsySfte+GiXMfiJbNhtyeLvBfgo8wHQYD
VR0OBBYEFG6+DdlJw+CC9BrBGP9aiyrIMTjRMAwGA1UdEwEB/wQCMAAwDgYDVR0P
AQH/BAQDAgeAMA0GCSqGSIb3DQEBCwUAA4IBAQB0IEgW43ZXGqOkMghI2HouGeut
lUmNtkSujGpiCKj+yTF4tJAUJnoM6ZJRZFgPAYmJguCxpP6gzZ+FguEHYwHzcq0Q
jVAs9vWJ85/YrTWOqV3yd+KNwRZjeosG+rWhyCQRCEQjVktLM4KS6fy5hYDCqnc9
h38n2mfexPRYeoF0Og4y2uvziY6DzKrPixahLzCNLYtCfOoDekjX2Vy6xqbDV25b
cLsVPEyq64SbMRzmUHN75R3VhlLoLqdbqv2YaHcxrOcGCKCRFjP9lk216PBnmMMb
/A1WGK41yba2vtbtx7D8otfF5jP3n+w1TXnSnCRi7NwuC/fvQm1oNOVE/0F/
-----END CERTIFICATE-----
)EOF";

// Private Key
const char AWS_CERT_PRIVATE[] PROGMEM = R"EOF(
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA2fdAo6cFjlUaWpV6orUGsUDzHbZO28e2boaxhSjXWk8L9xrn
chA4chfV8x8HATYLoPeRd2g48A29qYX+VWVX1OdHaGesf+fZecUi/79YrpqPMyni
gQ69FdsZ34vkvmpSQTA/1ICZGR67tXMLpN5OpHSWrOVCt/DLFo1w3UF/vru5KVB5
3PfJpmcUl044zeBc3bwXTSYAOz8ksPN++nPj5dRHa7Yic9mwMl18ER7Rv6qs/tNb
uQ3MSBkE6WHwyZxE3KpoazxmxjTusQwok/deFT0DEBn2WcR2eDM5SyDGfsFEwtPS
Vsy5ID35qfWcPeuWRKbQQfPLdHWCpcdAxJR1owIDAQABAoIBABIWABkUPNPIn/0w
NhLWLo36s7GddQGrmqmlJ4nDD8uAj5+bbeT7D5P4AlrAEla5Y1Gh+UINNdxFZ51v
buErHZSe9D/nilq6pEMEZpkOCY/DZ2p5aUAINwxfN9BizUI3lEewdztsyEdbU3wE
5cxyXdgrjG0gQN7+bfubFOhnDPCIf+GBzBn/37yxKYOZaU49/N2jmysMU1q8Gr63
lRfucR+Y6vItrtqDhVRwvLapYqDBhCelkB3FlSaXInPYcHBVvTlAcN3m+9M97LKz
2Ek8yoLyGZ8U9uoai3kppgrbeX55rqs3dbJemGcuBS9pfzaZwmmMLMH6Gh3VFjXK
8oMAFGECgYEA9ssCgumMYBFQiSEG248aJld80WA6j93uVW/kdB3vdCOm9wbx9913
SR+0nYiz/ulbpE4aY6hDyUypTRehLQ5XoWVdpokzokSFN+jKsEUrOdQkEDp9Vaxx
Ryf3fA1QLVemyFzcvsQ4AJx3zCMJzATEheOUCpn/tlkcp0+Ovp6jGQsCgYEA4hjt
8qEhtB/Tf6g65L8jFtAKUlKgwdm3Xar28sgDliu4QdeyUq/hzEnUaE5SGFCbEOvE
7//zNPgIkn0piuvXoYlMeCVEGKsH7/9PK225Cl/zWulDFsmwsqtqAWJGRaRdX9Pt
znkNSx7SrtMnAXXVw00V3WATJfaSMYnzMq+o5MkCgYB3UfPm45AxKm3rvwIXyXp1
Kzt357Sotj5zJGQqGAcb+djR+pOmqXbw7dlfiSatipn6OKDdqg8MFnqMgW414IdR
yzaaPB+wxrw6Kd1FmEur6/t7tSu/7l3eb15ipfUr1wMWQH+h5DDHat8o3Y/xCiUS
LtP2xDo0KaWG5xo243ArvQKBgQCuG2po08IjdfqlLEQl0DZSI+Q+3pgijuhQPg4q
iPGSG5qpQVN1rzEe4p+prt4zESdIEXa3Jg7/9ByNycpKyzBimVsEjhXxNQtIuf8a
P0UmAxtgH45lJu1luPBJnobkrBynZYiT3c3p0hOFQt6flkEFQwAaWBiGvGh5s3RO
zMwvWQKBgQC+Qbb0c+cZlgcTG/cyRQ/xkIS5rrDPy/g0B/klIJMWAKoIy+e5tBIo
6n4Ev29ZwrNMi8R+ig/rlY/09uO/fVH1wxltYlg15DreJ2zLGfrCWVQIjaquSMXY
Ib+Zf3ytG80g1jsnPMsR1rirHV5R109o+fQLpErN8mw20jeXbsRw+Q==
-----END RSA PRIVATE KEY-----
)EOF";

// ==========================================
// 3. HARDWARE PIN DEFINITIONS & MODULES
// ==========================================
#define DHTPIN D5
#define TRIG D6
#define ECHO D7
#define GREEN_LED D3
#define BLUE_LED D4
#define TANK_HEIGHT 30.0

LiquidCrystal_I2C lcd(0x27, 16, 2); // Initialized with default address 0x27
DHT11 dht11(DHTPIN);

// WiFi Clients
WiFiClientSecure wifiSecureClient; // Secure connection for AWS Core
WiFiClient localClient;             // Plain HTTP connection for local dashboard (very lightweight!)
PubSubClient mqttClient(wifiSecureClient);

// Thresholds & Status variables
String material = "PLA";
const float TEMP_LIMIT = 30.0;
const float HUM_LIMIT = 60.0;
const float LEVEL_LIMIT = 15.0;

// Variables to cache sensor readings
float currentTemp = 0.0;
float currentHum = 0.0;
float currentLevel = 0.0;
bool hasCurrentAlert = false;
bool isTempAlert = false;
bool isHumAlert = false;
bool isLevelAlert = false;

// Timing intervals (non-blocking)
unsigned long lastSensorReadTime = 0;
const unsigned long SENSOR_READ_INTERVAL = 5000; // Read sensors and publish every 5 seconds

unsigned long lastLCDCycleTime = 0;
const unsigned long LCD_CYCLE_INTERVAL = 3000;   // Cycle LCD pages every 3 seconds
int lcdPage = 0;

unsigned long lastWiFiCheckTime = 0;
const unsigned long WIFI_CHECK_INTERVAL = 10000;

// ==========================================
// 4. FUNCTION DEFINITIONS
// ==========================================

// Connect to WiFi network
void connectToWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);
  
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Connecting");
  
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);
  delay(100);
  WiFi.begin(ssid, password);
  
  int counter = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    lcd.setCursor(counter % 16, 1);
    lcd.print(".");
    counter++;
    if (counter > 30) { // Timeout after 15 seconds
      Serial.println("\nWiFi timeout! Operating offline.");
      lcd.clear();
      lcd.print("WiFi Offline");
      delay(1000);
      return;
    }
  }
  
  Serial.println("\nWiFi Connected successfully!");
  lcd.clear();
  lcd.print("WiFi Connected");
  delay(1000);
}

// Synchronize local time via SNTP (Required for AWS TLS Certificate Validation)
void syncTime() {
  Serial.print("Setting time using SNTP (for AWS SSL certificates)... ");
  lcd.clear();
  lcd.print("Syncing Time...");
  
  // Set timezone to UTC
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  time_t now = time(nullptr);
  
  int timeout = 0;
  while (now < 8 * 3600 * 2) {
    delay(500);
    Serial.print(".");
    now = time(nullptr);
    timeout++;
    if (timeout > 30) {
      Serial.println("\nFailed to sync time! AWS Core connection might fail.");
      lcd.clear();
      lcd.print("Time Sync Fail");
      delay(1000);
      return;
    }
  }
  
  Serial.println("\nTime synchronized successfully!");
  lcd.clear();
  lcd.print("Time Synced!");
  delay(1000);
}

// Connect to AWS IoT Core MQTT Broker
void connectToAWS() {
  if (!wifiSecureClient.loadCACert(AWS_CERT_CA)) {
    Serial.println("Error loading AWS Root CA!");
  }
  if (!wifiSecureClient.loadCertificate(AWS_CERT_CRT)) {
    Serial.println("Error loading AWS Client Cert!");
  }
  if (!wifiSecureClient.loadPrivateKey(AWS_CERT_PRIVATE)) {
    Serial.println("Error loading AWS Private Key!");
  }
  
  // BearSSL optimization: set custom buffer sizes to reduce RAM usage on ESP8266!
  wifiSecureClient.setBufferSizes(2048, 1024);
  
  mqttClient.setServer(aws_endpoint, aws_port);
  
  Serial.print("Connecting to AWS IoT Core... ");
  if (mqttClient.connect(client_id)) {
    Serial.println("Connected!");
  } else {
    Serial.print("Failed, rc=");
    Serial.println(mqttClient.state());
  }
}

// Read Distance from HC-SR04 sensor
float getDistance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long duration = pulseIn(ECHO, HIGH, 50000); // 50ms timeout
  if (duration == 0) return -1.0;
  return duration * 0.0343 / 2.0;
}

// Update the LCD display based on selected page
void updateLCD(int page) {
  lcd.clear();
  
  // Safety checks in case LCD init failed
  if (page == 0) {
    // Page 0: Readings Page
    lcd.setCursor(0, 0);
    lcd.print("T:"); lcd.print(currentTemp, 1); lcd.print("C  H:"); lcd.print(currentHum, 0); lcd.print("%");
    lcd.setCursor(0, 1);
    lcd.print("Lvl:"); lcd.print(currentLevel, 1); lcd.print("% ("); lcd.print(material); lcd.print(")");
  } 
  else if (page == 1) {
    // Page 1: System Health Status
    lcd.setCursor(0, 0);
    lcd.print("SYSTEM STATUS:");
    lcd.setCursor(0, 1);
    if (hasCurrentAlert) {
      lcd.print("⚠️ ALERT ACTIVE");
    } else {
      lcd.print("✅ SAFE & STABLE");
    }
  } 
  else if (page == 2) {
    // Page 2: Alerts detail page
    lcd.setCursor(0, 0);
    lcd.print("ACTIVE WARNINGS:");
    lcd.setCursor(0, 1);
    if (!isTempAlert && !isHumAlert && !isLevelAlert) {
      lcd.print("None - Safe");
    } else {
      if (isTempAlert) lcd.print("T ");
      if (isHumAlert) lcd.print("H ");
      if (isLevelAlert) lcd.print("L ");
      lcd.print("Warning!");
    }
  }
}

// ==========================================
// 5. MAIN SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(500);

  // Setup Sensor Pins
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);

  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BLUE_LED, LOW);

  // Initialize I2C and LCD
  Wire.begin(D2, D1); // SDA = D2, SCL = D1
  
  // Try LCD initialization
  lcd.begin(16, 2);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.print("REMAC system");
  lcd.setCursor(0, 1);
  lcd.print("Booting up...");
  delay(1500);

  // Connect to WiFi
  connectToWiFi();

  // If connected, sync time and prepare AWS connection
  if (WiFi.status() == WL_CONNECTED) {
    syncTime();
    connectToAWS();
  }

  // Pre-load sensors so the LCD doesn't show 0 at boot
  float temperature = dht11.readTemperature();
  float humidity = dht11.readHumidity();
  float distance = getDistance();
  
  if (!isnan(temperature)) currentTemp = temperature;
  if (!isnan(humidity)) currentHum = humidity;
  if (distance >= 0) {
    currentLevel = ((TANK_HEIGHT - distance) / TANK_HEIGHT) * 100.0;
    if (currentLevel < 0) currentLevel = 0.0;
    if (currentLevel > 100) currentLevel = 100.0;
  }
  
  // Draw initial page
  updateLCD(0);
}

void loop() {
  unsigned long currentMillis = millis();

  // Keep AWS MQTT connection alive
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) {
      Serial.print("AWS connection lost. Reconnecting... ");
      if (mqttClient.connect(client_id)) {
        Serial.println("Connected!");
      } else {
        Serial.println("Failed to reconnect.");
      }
    }
    mqttClient.loop();
  }

  // 1. Maintain WiFi Connection in background
  if (currentMillis - lastWiFiCheckTime >= WIFI_CHECK_INTERVAL) {
    lastWiFiCheckTime = currentMillis;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi disconnected! Attempting reconnect...");
      WiFi.begin(ssid, password);
    }
  }

  // 2. Read Sensors, Upload data, and Print to Serial every 5 seconds
  if (currentMillis - lastSensorReadTime >= SENSOR_READ_INTERVAL) {
    lastSensorReadTime = currentMillis;

    float temperature = dht11.readTemperature();
    float humidity = dht11.readHumidity();
    float distance = getDistance();
    float level = 0.0;

    // Safety checks
    if (isnan(temperature)) temperature = currentTemp; // Use cached if failed
    if (isnan(humidity)) humidity = currentHum;

    if (distance < 0) {
      level = currentLevel; // Use cached if failed
    } else {
      level = ((TANK_HEIGHT - distance) / TANK_HEIGHT) * 100.0;
      if (level > 100) level = 100.0;
      if (level < 0) level = 0.0;
    }

    // Set Alert flags
    isTempAlert = temperature > TEMP_LIMIT;
    isHumAlert = humidity > HUM_LIMIT;
    isLevelAlert = level < LEVEL_LIMIT;
    hasCurrentAlert = isTempAlert || isHumAlert || isLevelAlert;

    // LED Control
    if (hasCurrentAlert) {
      digitalWrite(GREEN_LED, LOW);
      digitalWrite(BLUE_LED, HIGH); // Blue LED means Alert active
    } else {
      digitalWrite(GREEN_LED, HIGH); // Green LED means Safe
      digitalWrite(BLUE_LED, LOW);
    }

    // Warnings description
    String statusStr = hasCurrentAlert ? "DANGER" : "SAFE";
    String alertStr = "None";
    if (isTempAlert && isHumAlert && isLevelAlert) alertStr = "High Temp + High Humid + Low Material";
    else if (isTempAlert && isHumAlert) alertStr = "High Temperature + High Humidity";
    else if (isTempAlert && isLevelAlert) alertStr = "High Temperature + Low Material";
    else if (isHumAlert && isLevelAlert) alertStr = "High Humidity + Low Material";
    else if (isTempAlert) alertStr = "High Temperature";
    else if (isHumAlert) alertStr = "High Humidity";
    else if (isLevelAlert) alertStr = "Low Material Level";

    // Cache values globally for LCD renderer
    currentTemp = temperature;
    currentHum = humidity;
    currentLevel = level;

    // Print to Serial Monitor
    Serial.println("==========================================");
    Serial.print("Temperature : "); Serial.print(temperature); Serial.println(" C");
    Serial.print("Humidity    : "); Serial.print(humidity); Serial.println(" %");
    Serial.print("Level       : "); Serial.print(level); Serial.println(" %");
    Serial.print("Alerts      : "); Serial.println(alertStr);

    // ==========================================
    // A. UPLOAD TO LOCAL DASHBOARD (HTTP port 3000)
    // ==========================================
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      String uploadUrl = "http://" + local_server_ip + ":" + String(local_server_port) + "/api/telemetry/" + String(UNIT_ID);
      
      // Initialize connection using standard unencrypted HTTP client
      http.begin(localClient, uploadUrl);
      http.addHeader("Content-Type", "application/json");

      String jsonPayload = "{";
      jsonPayload += "\"device\":\"REMAC_PET_001\",";
      jsonPayload += "\"timestamp\":\"" + String(millis() / 1000) + "s\",";
      jsonPayload += "\"temperature\":" + String(temperature, 1) + ",";
      jsonPayload += "\"humidity\":" + String(humidity, 1) + ",";
      jsonPayload += "\"distance\":" + String(distance, 1) + ",";
      jsonPayload += "\"material_level\":" + String(level, 1) + ",";
      jsonPayload += "\"status\":\"" + statusStr + "\",";
      jsonPayload += "\"active_alert\":\"" + alertStr + "\",";
      jsonPayload += "\"random_forest\":\"" + statusStr + "\",";
      jsonPayload += "\"isolation_forest\":\"" + String(hasCurrentAlert ? "ANOMALY" : "NORMAL") + "\",";
      jsonPayload += "\"temperature_risk\":" + String((temperature / 40.0) * 100, 1) + ",";
      jsonPayload += "\"humidity_risk\":" + String((humidity / 60.0) * 100, 1);
      jsonPayload += "}";

      Serial.print("Uploading to Dashboard... ");
      int httpResponseCode = http.PUT(jsonPayload); // PUT request updates our local dashboard server
      Serial.println(httpResponseCode);             // Will print 200 when successful!
      http.end();
    } else {
      Serial.println("Local upload skipped (WiFi not connected).");
    }

    // ==========================================
    // B. UPLOAD TO AWS IOT CORE (MQTT port 8883)
    // ==========================================
    if (WiFi.status() == WL_CONNECTED && mqttClient.connected()) {
      String awsPayload = "{";
      awsPayload += "\"device_id\":\"REMAC_PET_001\",";
      awsPayload += "\"temperature\":" + String(temperature, 1) + ",";
      awsPayload += "\"humidity\":" + String(humidity, 1) + ",";
      awsPayload += "\"proximity\":" + String(distance, 1) + ",";
      awsPayload += "\"material_level\":" + String(level, 1) + ",";
      awsPayload += "\"status\":\"" + statusStr + "\",";
      awsPayload += "\"active_alerts\":\"" + alertStr + "\"";
      awsPayload += "}";

      Serial.print("Publishing to AWS IoT Core... ");
      if (mqttClient.publish(aws_topic, awsPayload.c_str())) {
        Serial.println("OK");
      } else {
        Serial.println("Failed");
      }
    } else {
      Serial.println("AWS upload skipped (offline or not connected).");
    }
  }

  // 3. Cycle LCD screen pages every 3 seconds (non-blocking)
  if (currentMillis - lastLCDCycleTime >= LCD_CYCLE_INTERVAL) {
    lastLCDCycleTime = currentMillis;
    lcdPage = (lcdPage + 1) % 3;
    updateLCD(lcdPage);
  }
}
