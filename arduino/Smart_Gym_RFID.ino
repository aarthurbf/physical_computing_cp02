/**
 * Smart_Gym_RFID.ino — Smart Gym | CP02
 * Disciplina: Physical Computing (IoT & IoB) — FIAP
 *
 * Hardware necessário:
 *   - Arduino Uno / Nano (ou ESP32)
 *   - Módulo RFID RC522
 *   - LED verde (pino 7) e LED vermelho (pino 8) [opcional]
 *   - Buzzer (pino 6) [opcional]
 *
 * Conexões RC522 → Arduino Uno:
 *   SDA  → D10
 *   SCK  → D13
 *   MOSI → D11
 *   MISO → D12
 *   GND  → GND
 *   RST  → D9
 *   3.3V → 3.3V
 *
 * Protocolo Serial:
 *   Baud: 9600
 *   Saída: "UID: XX:XX:XX:XX"
 *
 * Bibliotecas necessárias (instalar via Library Manager):
 *   - MFRC522 by GithubCommunity
 *   - SPI (nativa)
 */

#include <SPI.h>
#include <MFRC522.h>

// Pinos
#define SS_PIN    10
#define RST_PIN    9
#define LED_VERDE  7
#define LED_VERM   8
#define BUZZER     6

// Objetos
MFRC522 rfid(SS_PIN, RST_PIN);

// Debounce
String ultimoUID    = "";
unsigned long tUlt  = 0;
const unsigned long DEBOUNCE_MS = 2000;

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();

  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_VERM,  OUTPUT);
  pinMode(BUZZER,    OUTPUT);

  // Pisca LEDs para indicar boot
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_VERDE, HIGH);
    delay(100);
    digitalWrite(LED_VERDE, LOW);
    delay(100);
  }

  Serial.println("Smart Gym RFID Pronto.");
  Serial.println("Aguardando cartao...");
}

void loop() {
  // Verifica se há novo cartão
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  // Monta string do UID no formato XX:XX:XX:XX
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
    if (i < rfid.uid.size - 1) uid += ":";
  }
  uid.toUpperCase();

  // Debounce — ignora leitura do mesmo cartão em menos de 2 s
  unsigned long agora = millis();
  if (uid == ultimoUID && (agora - tUlt) < DEBOUNCE_MS) {
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    return;
  }

  ultimoUID = uid;
  tUlt      = agora;

  // Envia para o Python no formato esperado: "UID: XX:XX:XX:XX"
  Serial.print("UID: ");
  Serial.println(uid);

  // Feedback visual
  beep(1, 100);
  digitalWrite(LED_VERDE, HIGH);
  delay(300);
  digitalWrite(LED_VERDE, LOW);

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

void beep(int vezes, int duracao_ms) {
  for (int i = 0; i < vezes; i++) {
    digitalWrite(BUZZER, HIGH);
    delay(duracao_ms);
    digitalWrite(BUZZER, LOW);
    if (i < vezes - 1) delay(100);
  }
}
