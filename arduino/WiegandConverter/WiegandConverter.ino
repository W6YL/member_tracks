/*
 * Example on how to use the Wiegand reader library with interruptions.
 */

#include <Wiegand.h>

// These are the pins connected to the Wiegand D0 and D1 signals.
// Ensure your board supports external Interruptions on these pins
#define PIN_D0 2
#define PIN_D1 3

#define PIN_D0_OUTSIDE 20
#define PIN_D1_OUTSIDE 21

// The object that handles the wiegand protocol
Wiegand wiegand;
Wiegand wiegand_outside;

bool debug = false;

// Initialize Wiegand reader
void setup() {
  Serial.begin(9600);

  //Install listeners and initialize Wiegand reader
  wiegand.onReceive(receivedData, (void*)0x01);
  wiegand.onReceiveError(receivedDataError, (void*)0x01);
  wiegand.onStateChange(stateChanged,(void*) 0x01);
  wiegand.begin(Wiegand::LENGTH_ANY, true);

  wiegand_outside.onReceive(receivedData, (void*)0x02);
  wiegand_outside.onReceiveError(receivedDataError, (void*)0x02);
  wiegand_outside.onStateChange(stateChanged, (void*)0x02);
  wiegand_outside.begin(Wiegand::LENGTH_ANY, true);

  //initialize pins as INPUT and attaches interruptions
  pinMode(PIN_D0, INPUT);
  pinMode(PIN_D1, INPUT);
  pinMode(PIN_D0_OUTSIDE, INPUT);
  pinMode(PIN_D1_OUTSIDE, INPUT);

  attachInterrupt(digitalPinToInterrupt(PIN_D0), pinStateChanged_inside, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_D1), pinStateChanged_inside, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_D0_OUTSIDE), pinStateChanged_outside, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_D1_OUTSIDE), pinStateChanged_outside, CHANGE);

  //Sends the initial pin state to the Wiegand library
  pinStateChanged_inside();
  pinStateChanged_outside();
}

// Every few milliseconds, check for pending messages on the wiegand reader
// This executes with interruptions disabled, since the Wiegand library is not thread-safe
void loop() {
  noInterrupts();
  wiegand.flush();
  wiegand_outside.flush();
  interrupts();
  //Sleep a little -- this doesn't have to run very often.
  delay(100);
}

// When any of the pins have changed, update the state of the wiegand library
void pinStateChanged_inside() {
  wiegand.setPin0State(digitalRead(PIN_D0));
  wiegand.setPin1State(digitalRead(PIN_D1));
}

// When any of the pins have changed, update the state of the wiegand library
void pinStateChanged_outside() {
  wiegand_outside.setPin0State(digitalRead(PIN_D0_OUTSIDE));
  wiegand_outside.setPin1State(digitalRead(PIN_D1_OUTSIDE));
}

// Notifies when a reader has been connected or disconnected.
// Instead of a message, the seconds parameter can be anything you want -- Whatever you specify on `wiegand.onStateChange()`
void stateChanged(bool plugged, void* readerID) {
    if (debug) {
      Serial.print("State Changed: (");
      Serial.print(reinterpret_cast<size_t>(readerID));
      Serial.print(") is ");
      Serial.println(plugged ? "CONNECTED" : "DISCONNECTED");
    } else {
      Serial.write(0x01); // State message
      Serial.write(reinterpret_cast<size_t>(readerID)); // Transmit the reader ID
      Serial.write(plugged ? 0x01 : 0x00); // 0x01 = Connected 0x02 = Disconnected
    }
}

// Notifies when a card was read.
// Instead of a message, the seconds parameter can be anything you want -- Whatever you specify on `wiegand.onReceive()`
void receivedData(uint8_t* data, uint8_t bits, void* readerID) {  
    uint8_t bytes = (bits+7)/8;
    if (debug) {
      Serial.print("Data RX: (");
      Serial.print(reinterpret_cast<size_t>(readerID));
      Serial.print(") num_bytes: ");
      Serial.print(bytes);
      Serial.print(" DATA_BYTES: ");
    } else {
      Serial.write(0x02); // Data RX
      Serial.write(reinterpret_cast<size_t>(readerID)); // Transmit the reader ID
      Serial.write(bytes);
    }

    for (int i=0; i<bytes; i++) {
        if (debug) {
          Serial.print(data[i]);
          Serial.print(" ");
          continue;
        }
        Serial.write(data[i]);
    }
    if (debug) {
      Serial.println(" END_DATA");
    }
}

// Notifies when an invalid transmission is detected
void receivedDataError(Wiegand::DataError error, uint8_t* rawData, uint8_t rawBits, void* readerID) {
    receivedData(rawData, rawBits, readerID);
}