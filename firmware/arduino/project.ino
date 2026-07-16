const byte PIN_COUNT = 8;

byte scanPins[PIN_COUNT] = {2, 3, 4, 5, 6, 7, 8, 9};

const byte GREEN_LED_PIN = 10;
const byte RED_LED_PIN = 11;

const unsigned long LED_ON_TIME = 1000;
const unsigned long debounceDelay = 180;

String lastPair = "";
String serialCommand = "";

unsigned long lastReportTime = 0;
unsigned long greenLedOffTime = 0;
unsigned long redLedOffTime = 0;

void setAllInputPullup() {
  for (byte i = 0; i < PIN_COUNT; i++) {
    pinMode(scanPins[i], INPUT_PULLUP);
  }
}

String makePair(byte a, byte b) {
  byte p1 = scanPins[a];
  byte p2 = scanPins[b];

  if (p1 > p2) {
    byte temp = p1;
    p1 = p2;
    p2 = temp;
  }

  return String(p1) + "," + String(p2);
}

String scanPressedPair() {
  for (byte i = 0; i < PIN_COUNT; i++) {
    setAllInputPullup();

    pinMode(scanPins[i], OUTPUT);
    digitalWrite(scanPins[i], LOW);

    delayMicroseconds(60);

    for (byte j = 0; j < PIN_COUNT; j++) {
      if (i == j) continue;

      if (digitalRead(scanPins[j]) == LOW) {
        return makePair(i, j);
      }
    }
  }

  return "";
}

void turnOffStatusLeds() {
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  greenLedOffTime = 0;
  redLedOffTime = 0;
}

void showSuccessLed() {
  turnOffStatusLeds();
  digitalWrite(GREEN_LED_PIN, HIGH);
  greenLedOffTime = millis() + LED_ON_TIME;
}

void showFailLed() {
  turnOffStatusLeds();
  digitalWrite(RED_LED_PIN, HIGH);
  redLedOffTime = millis() + LED_ON_TIME;
}

void updateLeds() {
  unsigned long now = millis();

  if (greenLedOffTime > 0 && now >= greenLedOffTime) {
    digitalWrite(GREEN_LED_PIN, LOW);
    greenLedOffTime = 0;
  }

  if (redLedOffTime > 0 && now >= redLedOffTime) {
    digitalWrite(RED_LED_PIN, LOW);
    redLedOffTime = 0;
  }
}

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd == "SUCCESS") {
    showSuccessLed();
    Serial.println("LED:GREEN");
  } else if (cmd == "FAIL") {
    showFailLed();
    Serial.println("LED:RED");
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (serialCommand.length() > 0) {
        handleCommand(serialCommand);
        serialCommand = "";
      }
    } else {
      serialCommand += c;

      if (serialCommand.length() > 30) {
        serialCommand = "";
      }
    }
  }
}

void setup() {
  Serial.begin(9600);
  delay(1000);

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);

  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);

  setAllInputPullup();

  Serial.println("READY MATRIX LED FINAL");
}

void loop() {
  readSerialCommands();
  updateLeds();

  String pair = scanPressedPair();
  unsigned long now = millis();

  if (pair != "") {
    if (pair != lastPair && now - lastReportTime > debounceDelay) {
      Serial.print("PAIR:");
      Serial.println(pair);

      lastPair = pair;
      lastReportTime = now;
    }
  } else {
    lastPair = "";
  }
}
