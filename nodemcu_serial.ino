#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <DHT11.h>

// ==========================================
// 1. PIN DEFINITIONS & MODULES
// ==========================================
#define DHTPIN D5
#define TRIG D6
#define ECHO D7
#define GREEN_LED D3
#define BLUE_LED D4
#define TANK_HEIGHT 30.0

LiquidCrystal_I2C lcd(0x27, 16, 2); // Initialized with default address 0x27
DHT11 dht11(DHTPIN);

// Cached sensor readings
float currentTemp = 0.0;
float currentHum = 0.0;
float currentLevel = 0.0;

bool hasCurrentAlert = false;
bool isTempAlert = false;
bool isHumAlert = false;
bool isLevelAlert = false;

const float TEMP_LIMIT = 30.0;
const float HUM_LIMIT = 60.0;
const float LEVEL_LIMIT = 15.0;

// Timing intervals
unsigned long lastSensorReadTime = 0;
const unsigned long SENSOR_READ_INTERVAL = 2000; // Read sensors every 2 seconds

unsigned long lastLCDCycleTime = 0;
const unsigned long LCD_CYCLE_INTERVAL = 3000;   // Cycle LCD pages every 3 seconds
int lcdPage = 0;

// ==========================================
// 2. HELPER FUNCTIONS
// ==========================================

// Read distance from Ultrasonic HC-SR04
float getDistance() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  long duration = pulseIn(ECHO, HIGH, 30000); // 30ms timeout
  if (duration == 0) return -1.0;
  return duration * 0.0343 / 2.0;
}

// Update text on I2C LCD Display
void updateLCD(int page) {
  lcd.clear();
  
  if (page == 0) {
    // Page 0: Live Readings
    lcd.setCursor(0, 0);
    lcd.print("T:"); lcd.print(currentTemp, 1); lcd.print("C H:"); lcd.print(currentHum, 0); lcd.print("%");
    lcd.setCursor(0, 1);
    lcd.print("Lvl:"); lcd.print(currentLevel, 1); lcd.print("% PLA");
  } 
  else if (page == 1) {
    // Page 1: System Status
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
    // Page 2: Warnings list
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
// 3. MAIN SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(115200);
  
  // Setup hardware pins
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BLUE_LED, OUTPUT);

  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BLUE_LED, LOW);

  // Initialize I2C and LCD
  Wire.begin(D2, D1); // SDA = D2, SCL = D1
  
  // Attempt robust LCD init
  lcd.begin(16, 2);
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.print("REMAC system");
  lcd.setCursor(0, 1);
  lcd.print("Booting up...");
  delay(1500);

  // Read sensors immediately so LCD has data right away
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
  
  updateLCD(0);
}

void loop() {
  unsigned long currentMillis = millis();

  // 1. Read Sensors and output data to USB Serial every 2 seconds
  if (currentMillis - lastSensorReadTime >= SENSOR_READ_INTERVAL) {
    lastSensorReadTime = currentMillis;

    float temperature = dht11.readTemperature();
    float humidity = dht11.readHumidity();
    float distance = getDistance();
    float level = 0.0;

    // Load cached value if sensor fails to read
    if (isnan(temperature)) temperature = currentTemp; 
    if (isnan(humidity)) humidity = currentHum;

    if (distance < 0) {
      level = currentLevel; 
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

    // LED indicators
    if (hasCurrentAlert) {
      digitalWrite(GREEN_LED, LOW);
      digitalWrite(BLUE_LED, HIGH); 
    } else {
      digitalWrite(GREEN_LED, HIGH); 
      digitalWrite(BLUE_LED, LOW);
    }

    // Cache readings locally
    currentTemp = temperature;
    currentHum = humidity;
    currentLevel = level;

    // Format sensor data as a simple JSON string over Serial
    Serial.print("DATA:");
    Serial.print("{\"temperature\":"); Serial.print(temperature, 1);
    Serial.print(",\"humidity\":"); Serial.print(humidity, 1);
    Serial.print(",\"distance\":"); Serial.print(distance, 1);
    Serial.print(",\"material_level\":"); Serial.print(level, 1);
    Serial.println("}");
  }

  // 2. Cycle LCD display screens every 3 seconds
  if (currentMillis - lastLCDCycleTime >= LCD_CYCLE_INTERVAL) {
    lastLCDCycleTime = currentMillis;
    lcdPage = (lcdPage + 1) % 3;
    updateLCD(lcdPage);
  }
}
