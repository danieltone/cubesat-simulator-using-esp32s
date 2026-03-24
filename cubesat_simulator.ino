#include <WiFi.h>
#include <esp_now.h>
#include <math.h>

// --------------------------
// CubeSat simulator settings
// --------------------------
static const char *SIM_NAME = "XIAO-C3-CUBESAT-SIM";
static const uint32_t HEARTBEAT_MS = 15000;

// Set true to send JSON via ESP-NOW to a ground station ESP32 (no router needed).
// Keep false if you only want Serial JSON output.
static const bool ENABLE_ESPNOW = false;

// Replace with receiver ESP32 MAC address if ENABLE_ESPNOW = true.
static uint8_t GROUND_STATION_MAC[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, 0x00};

static uint32_t bootMs = 0;
static uint32_t lastHeartbeatMs = 0;
static bool espNowReady = false;

// Simple xorshift PRNG for deterministic pseudo-noise (better than random jitter from millis()).
static uint32_t rngState = 0xC0BE5A7u;

float frandUnit() {
  // Returns [-1, +1]
  rngState ^= rngState << 13;
  rngState ^= rngState >> 17;
  rngState ^= rngState << 5;
  float norm = (rngState & 0xFFFF) / 65535.0f;
  return (norm * 2.0f) - 1.0f;
}

float clampf(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

float wrapDeg(float deg) {
  while (deg > 180.0f) deg -= 360.0f;
  while (deg < -180.0f) deg += 360.0f;
  return deg;
}

float wrap360(float deg) {
  while (deg >= 360.0f) deg -= 360.0f;
  while (deg < 0.0f) deg += 360.0f;
  return deg;
}

void onEspNowSent(const uint8_t *macAddr, esp_now_send_status_t status) {
  Serial.printf("{\"event\":\"tx_status\",\"ok\":%s,\"to\":\"%02X:%02X:%02X:%02X:%02X:%02X\"}\n",
                (status == ESP_NOW_SEND_SUCCESS) ? "true" : "false",
                macAddr[0], macAddr[1], macAddr[2], macAddr[3], macAddr[4], macAddr[5]);
}

bool initEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true, true);

  if (esp_now_init() != ESP_OK) {
    Serial.println("{\"event\":\"error\",\"msg\":\"esp_now_init failed\"}");
    return false;
  }

  esp_now_register_send_cb(onEspNowSent);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, GROUND_STATION_MAC, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("{\"event\":\"error\",\"msg\":\"esp_now_add_peer failed\"}");
    return false;
  }

  return true;
}

void setup() {
  Serial.begin(115200);
  delay(600);

  bootMs = millis();
  lastHeartbeatMs = 0;

  Serial.printf("{\"event\":\"boot\",\"node\":\"%s\",\"heartbeat_s\":%lu}\n",
                SIM_NAME,
                HEARTBEAT_MS / 1000UL);

  if (ENABLE_ESPNOW) {
    espNowReady = initEspNow();
    Serial.printf("{\"event\":\"transport\",\"name\":\"esp_now\",\"enabled\":%s}\n",
                  espNowReady ? "true" : "false");
  } else {
    Serial.println("{\"event\":\"transport\",\"name\":\"serial_only\",\"enabled\":true}");
  }
}

String buildTelemetryJson(uint32_t nowMs) {
  const float tSec = (nowMs - bootMs) / 1000.0f;

  // LEO assumptions (typical educational CubeSat):
  const float orbitalPeriodSec = 95.0f * 60.0f;
  const float inclinationDeg = 51.6f;
  const float meanAltitudeKm = 525.0f;

  const float orbitPhase = fmodf(tSec / orbitalPeriodSec, 1.0f);
  const float theta = orbitPhase * 2.0f * PI;

  const float altitudeKm = meanAltitudeKm + 2.8f * sinf(theta * 0.2f) + 0.2f * frandUnit();
  const float latitudeDeg = inclinationDeg * sinf(theta) + 0.15f * frandUnit();
  const float longitudeDeg = wrapDeg((orbitPhase * 360.0f * 15.0f) - 180.0f + 0.2f * frandUnit());

  // Approx eclipse fraction for LEO (~35-40%).
  const bool inEclipse = (orbitPhase > 0.31f && orbitPhase < 0.68f);

  // EPS model
  const float solarW = inEclipse ? 0.0f : (5.4f + 0.4f * sinf(theta * 2.0f) + 0.2f * frandUnit());
  const float loadW = 2.4f + 0.35f * sinf(theta * 1.4f) + 0.15f * frandUnit();
  float batterySoc = 76.0f + 10.0f * sinf(theta - 0.7f);
  if (inEclipse) {
    batterySoc -= 6.0f;
  }
  batterySoc = clampf(batterySoc, 18.0f, 99.0f);

  const float batteryVoltage = 3.55f + 0.65f * (batterySoc / 100.0f) + 0.02f * frandUnit();
  const float batteryCurrentA = clampf((solarW - loadW) / 3.7f, -1.4f, 1.4f);

  // Thermal model
  const float sunBias = inEclipse ? -1.0f : 1.0f;
  const float busTempC = 18.0f + sunBias * 7.5f + 1.2f * sinf(theta * 1.3f) + 0.5f * frandUnit();
  const float battTempC = 15.0f + sunBias * 4.2f + 0.8f * sinf(theta * 0.9f) + 0.4f * frandUnit();
  const float payloadTempC = 22.0f + sunBias * 6.0f + 1.4f * sinf(theta * 1.8f) + 0.5f * frandUnit();

  // ADCS model
  const float rollDeg = 2.5f * sinf(theta * 0.7f) + 0.3f * frandUnit();
  const float pitchDeg = 1.8f * cosf(theta * 0.8f) + 0.3f * frandUnit();
  const float yawDeg = wrap360(orbitPhase * 360.0f + 1.0f * sinf(theta * 0.2f));

  const float wx = 0.03f + 0.01f * frandUnit();
  const float wy = 0.02f + 0.01f * frandUnit();
  const float wz = 0.04f + 0.01f * frandUnit();

  const float magX_uT = 28.0f * sinf(theta) + 1.0f * frandUnit();
  const float magY_uT = 25.0f * cosf(theta) + 1.0f * frandUnit();
  const float magZ_uT = 18.0f * sinf(theta * 0.5f) + 0.8f * frandUnit();

  const float sunVecX = inEclipse ? 0.0f : clampf(cosf(theta), -1.0f, 1.0f);
  const float sunVecY = inEclipse ? 0.0f : clampf(sinf(theta), -1.0f, 1.0f);
  const float sunVecZ = inEclipse ? 0.0f : 0.12f;

  // Comms status (simulated)
  const float downlinkSnrDb = 9.5f + 3.0f * sinf(theta * 1.1f) + 0.4f * frandUnit();
  const int downlinkRssiDbm = (int)(-111.0f + 7.0f * sinf(theta * 0.9f) + 1.2f * frandUnit());
  const int downlinkBps = 9600;

  char json[1400];
  snprintf(
    json,
    sizeof(json),
    "{"
      "\"type\":\"telemetry\"," 
      "\"node\":\"%s\"," 
      "\"mission_time_s\":%.1f," 
      "\"heartbeat_s\":%lu," 
      "\"orbit\":{" 
        "\"regime\":\"LEO\"," 
        "\"altitude_km\":%.2f," 
        "\"inclination_deg\":%.1f," 
        "\"latitude_deg\":%.3f," 
        "\"longitude_deg\":%.3f," 
        "\"eclipse\":%s"
      "},"
      "\"eps\":{" 
        "\"battery_soc_pct\":%.2f," 
        "\"battery_v\":%.3f," 
        "\"battery_i_a\":%.3f," 
        "\"solar_w\":%.2f," 
        "\"load_w\":%.2f"
      "},"
      "\"thermal\":{" 
        "\"bus_c\":%.2f," 
        "\"battery_c\":%.2f," 
        "\"payload_c\":%.2f"
      "},"
      "\"adcs\":{" 
        "\"attitude_euler_deg\":{\"roll\":%.2f,\"pitch\":%.2f,\"yaw\":%.2f},"
        "\"gyro_dps\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},"
        "\"mag_uT\":{\"x\":%.2f,\"y\":%.2f,\"z\":%.2f},"
        "\"sun_vec\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f}"
      "},"
      "\"comms\":{" 
        "\"downlink_bps\":%d," 
        "\"snr_db\":%.2f," 
        "\"rssi_dbm\":%d"
      "},"
      "\"health\":{" 
        "\"watchdog_reset\":false," 
        "\"fault\":false"
      "}"
    "}",
    SIM_NAME,
    tSec,
    HEARTBEAT_MS / 1000UL,
    altitudeKm,
    inclinationDeg,
    latitudeDeg,
    longitudeDeg,
    inEclipse ? "true" : "false",
    batterySoc,
    batteryVoltage,
    batteryCurrentA,
    solarW,
    loadW,
    busTempC,
    battTempC,
    payloadTempC,
    rollDeg,
    pitchDeg,
    yawDeg,
    wx,
    wy,
    wz,
    magX_uT,
    magY_uT,
    magZ_uT,
    sunVecX,
    sunVecY,
    sunVecZ,
    downlinkBps,
    downlinkSnrDb,
    downlinkRssiDbm);

  return String(json);
}

String buildCompactLinkJson(const String &fullJson, uint32_t nowMs) {
  const float tSec = (nowMs - bootMs) / 1000.0f;
  // Compact, link-friendly frame for ESP-NOW. Keep under ~220 bytes.
  // Includes key heartbeat + state values only.
  // Full JSON remains available on Serial.
  float phase = fmodf(tSec / (95.0f * 60.0f), 1.0f);
  float lat = 51.6f * sinf(phase * 2.0f * PI);
  float lon = wrapDeg((phase * 360.0f * 15.0f) - 180.0f);
  bool eclipse = (phase > 0.31f && phase < 0.68f);

  char compact[240];
  snprintf(compact,
           sizeof(compact),
           "{\"t\":\"hb\",\"node\":\"%s\",\"mt\":%.0f,\"lat\":%.2f,\"lon\":%.2f,\"e\":%s,\"src\":\"espnow\"}",
           SIM_NAME,
           tSec,
           lat,
           lon,
           eclipse ? "true" : "false");
  (void)fullJson;
  return String(compact);
}

void transmitTelemetry(const String &json, uint32_t nowMs) {
  Serial.println(json);

  if (ENABLE_ESPNOW && espNowReady) {
    String compact = buildCompactLinkJson(json, nowMs);
    const uint8_t *payload = reinterpret_cast<const uint8_t *>(compact.c_str());
    size_t len = compact.length();
    if (len > 240) {
      Serial.println("{\"event\":\"warn\",\"msg\":\"compact esp_now frame too long\"}");
      return;
    }
    esp_err_t tx = esp_now_send(GROUND_STATION_MAC, payload, len);
    if (tx != ESP_OK) {
      Serial.printf("{\"event\":\"error\",\"msg\":\"esp_now_send failed\",\"code\":%d}\n", (int)tx);
    }
  }
}

void loop() {
  uint32_t nowMs = millis();
  if ((nowMs - lastHeartbeatMs) >= HEARTBEAT_MS) {
    lastHeartbeatMs = nowMs;
    String telemetry = buildTelemetryJson(nowMs);
    transmitTelemetry(telemetry, nowMs);
  }
}
