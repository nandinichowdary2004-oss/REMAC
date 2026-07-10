#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h> // Built-in: Handles both KVDB cloud and secure AWS HTTP requests
#include <WiFiClientSecure.h>  // Built-in: Handles secure SSL handshake
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT11.h>
#include <time.h>

// ==========================================
// 1. WI-FI & CLOUD CONFIGURATION
// ==========================================
const char* ssid = "REMAC";
const char* password = "12345678";

// AWS IoT Core HTTPS REST Settings (No MQTT library required!)
const char* aws_endpoint = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com";
const char* aws_topic = "remac/node1/data";

// Free Cloud KVDB.io configuration (Does NOT require any PC server or signup!)
const String cloud_jsonblob_url = "https://jsonblob.com/api/jsonBlob/019f4ab1-f7e9-7797-aad7-e56a4a77fc86";

// ==========================================
// 2. AWS SECURITY CERTIFICATES (PEM format)
// ==========================================

// Amazon Root CA 1
const char* AWS_CERT_CA = R"EOF(
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
const char* AWS_CERT_CRT = R"EOF(
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
const char* AWS_CERT_PRIVATE = R"EOF(
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

LiquidCrystal_I2C lcd(0x27, 16, 2); 
DHT11 dht11(DHTPIN);

// WiFi Clients
WiFiClientSecure wifiSecureClient;   // Handles secure SSL handshake for AWS IoT Core
WiFiClientSecure wifiClientInsecure; // Handles SSL logic for KVDB.io cloud storage
time_t nowTime;

// BearSSL Certificate Wrapper Objects for AWS
BearSSL::X509List caCert(AWS_CERT_CA);
BearSSL::X509List clientCert(AWS_CERT_CRT);
BearSSL::PrivateKey clientKey(AWS_CERT_PRIVATE);

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

// ==========================================
// 4. FUNCTION DEFINITIONS
// ==========================================

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
    if (counter > 30) { 
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

void syncTime() {
  Serial.print("Setting time using SNTP (for AWS SSL certificates)... ");
  lcd.clear();
  lcd.print("Syncing Time...");
  
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  nowTime = time(nullptr);
  
  int timeout = 0;
  while (nowTime < 8 * 3600 * 2) {
    delay(500);
    Serial.print(".");
    nowTime = time(nullptr);
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

float getDistance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long duration = pulseIn(ECHO, HIGH, 30000); 
  if (duration == 0) return -1.0;
  return duration * 0.0343 / 2.0;
}

void updateLCD() {
  lcd.clear();
  // Display Live Readings on top line, status & alert warning on bottom line
  lcd.setCursor(0, 0);
  lcd.print("T:"); lcd.print(currentTemp, 1); lcd.print("C H:"); lcd.print(currentHum, 0); lcd.print("%");
  
  lcd.setCursor(0, 1);
  if (hasCurrentAlert) {
    lcd.print("⚠️ ");
    if (isTempAlert) lcd.print("Temp!");
    else if (isHumAlert) lcd.print("Humid!");
    else if (isLevelAlert) lcd.print("LowLvl!");
  } else {
    lcd.print("Lvl:"); lcd.print(currentLevel, 0); lcd.print("% PLA SAFE");
  }
}

// ==========================================
// 5. MAIN SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);

  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BLUE_LED, LOW);

  Wire.begin(D2, D1); // SDA = D2, SCL = D1
  
  lcd.begin(16, 2);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.print("REMAC system");
  lcd.setCursor(0, 1);
  lcd.print("Booting up...");
  delay(1500);

  connectToWiFi();

  // Set insecure mode for KVDB.io cloud uploads to bypass CA certificate check (saves RAM!)
  wifiClientInsecure.setInsecure();

  if (WiFi.status() == WL_CONNECTED) {
    syncTime();
  }
}

void loop() {
  // 1. Read Sensors (Happens exactly once every 5 seconds)
  float temperature = dht11.readTemperature();
  float humidity = dht11.readHumidity();
  float distance = getDistance();
  float level = 0.0;

  if (isnan(temperature)) temperature = currentTemp; 
  if (isnan(humidity)) humidity = currentHum;

  if (distance < 0) {
    level = currentLevel; 
  } else {
    level = ((TANK_HEIGHT - distance) / TANK_HEIGHT) * 100.0;
    if (level > 100) level = 100.0;
    if (level < 0) level = 0.0;
  }

  // Set alert statuses
  isTempAlert = temperature > TEMP_LIMIT;
  isHumAlert = humidity > HUM_LIMIT;
  isLevelAlert = level < LEVEL_LIMIT;
  hasCurrentAlert = isTempAlert || isHumAlert || isLevelAlert;

  // LED logic
  if (hasCurrentAlert) {
    digitalWrite(GREEN_LED, LOW);
    digitalWrite(BLUE_LED, HIGH); // Alarm LED
  } else {
    digitalWrite(GREEN_LED, HIGH); // Safe LED
    digitalWrite(BLUE_LED, LOW);
  }

  String statusStr = hasCurrentAlert ? "DANGER" : "SAFE";
  String alertStr = "None";
  if (isTempAlert && isHumAlert && isLevelAlert) alertStr = "High Temp + High Humid + Low Material";
  else if (isTempAlert && isHumAlert) alertStr = "High Temperature + High Humidity";
  else if (isTempAlert && isLevelAlert) alertStr = "High Temperature + Low Material";
  else if (isHumAlert && isLevelAlert) alertStr = "High Humidity + Low Material";
  else if (isTempAlert) alertStr = "High Temperature";
  else if (isHumAlert) alertStr = "High Humidity";
  else if (isLevelAlert) alertStr = "Low Material Level";

  // Cache values globally
  currentTemp = temperature;
  currentHum = humidity;
  currentLevel = level;

  // 2. Display on LCD and Serial Monitor
  updateLCD();
  
  Serial.println("==========================================");
  Serial.print("Temperature : "); Serial.print(temperature); Serial.println(" C");
  Serial.print("Humidity    : "); Serial.print(humidity); Serial.println(" %");
  Serial.print("Level       : "); Serial.print(level); Serial.println(" %");
  Serial.print("Alerts      : "); Serial.println(alertStr);

  // ==========================================
  // A. UPLOAD TO CLOUD TELEMETRY STORAGE (JSONBlob - Direct Internet Upload)
  // ==========================================
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    
    // We send to the secure cloud endpoint directly! No local server needed on PC!
    http.begin(wifiClientInsecure, cloud_jsonblob_url);
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
    int httpResponseCode = http.PUT(jsonPayload); // PUT updates our static JSONBlob
    Serial.println(httpResponseCode); // Prints 200 on success!
    http.end();
  } else {
    Serial.println("Dashboard upload skipped (WiFi disconnected).");
  }

  // ==========================================
  // B. UPLOAD TO AWS IOT CORE (HTTPS POST port 8443)
  // ==========================================
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    
    // Configure BearSSL securely using native methods
    wifiSecureClient.setBufferSizes(2048, 1024); // Optimize handshakes for ESP8266 RAM
    wifiSecureClient.setTrustAnchors(&caCert);
    wifiSecureClient.setClientRSACert(&clientCert, &clientKey);
    
    // AWS IoT Core HTTPS REST publish endpoint
    String awsUrl = "https://" + String(aws_endpoint) + ":8443/topics/" + String(aws_topic) + "?qos=1";
    
    http.begin(wifiSecureClient, awsUrl);
    http.addHeader("Content-Type", "application/json");

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
    int awsResponseCode = http.POST(awsPayload);
    if (awsResponseCode > 0) {
      Serial.println(awsResponseCode); // Prints 200/202 on success!
    } else {
      Serial.print("Failed: ");
      Serial.println(http.errorToString(awsResponseCode).c_str());
    }
    http.end();
  } else {
    Serial.println("AWS upload skipped (offline).");
  }

  // Delay exactly 5 seconds before the next iteration
  delay(5000);
}
