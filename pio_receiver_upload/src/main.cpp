#include <WiFi.h>
#include <esp_now.h>
#include <esp_idf_version.h>
#include <esp_wifi.h>

static const uint8_t ESPNOW_CHANNEL = 1;

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5, 0, 0)
void onReceive(const esp_now_recv_info_t *info, const uint8_t *data, int dataLen) {
  const uint8_t *src = info->src_addr;
#else
void onReceive(const uint8_t *src, const uint8_t *data, int dataLen) {
#endif
  Serial.printf("{\"event\":\"rx\",\"from\":\"%02X:%02X:%02X:%02X:%02X:%02X\",\"len\":%d,\"payload\":",
                src[0], src[1], src[2],
                src[3], src[4], src[5],
                dataLen);

  Serial.print("\"");
  for (int i = 0; i < dataLen; i++) {
    char c = (char)data[i];
    if (c == '"' || c == '\\') {
      Serial.print('\\');
    }
    Serial.print(c);
  }
  Serial.println("\"}");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  Serial.printf("{\"event\":\"ground_boot\",\"mac\":\"%s\"}\n", WiFi.macAddress().c_str());

  if (esp_now_init() != ESP_OK) {
    Serial.println("{\"event\":\"error\",\"msg\":\"esp_now_init failed\"}");
    return;
  }

  esp_now_register_recv_cb(onReceive);
  Serial.println("{\"event\":\"ready\",\"transport\":\"esp_now\"}");
}

void loop() {
  delay(50);
}
