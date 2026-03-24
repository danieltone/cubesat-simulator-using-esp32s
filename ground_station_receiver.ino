#include <WiFi.h>
#include <esp_now.h>

void onReceive(const esp_now_recv_info_t *info, const uint8_t *data, int dataLen) {
  Serial.printf("{\"event\":\"rx\",\"from\":\"%02X:%02X:%02X:%02X:%02X:%02X\",\"len\":%d,\"payload\":",
                info->src_addr[0], info->src_addr[1], info->src_addr[2],
                info->src_addr[3], info->src_addr[4], info->src_addr[5],
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
  WiFi.disconnect(true, true);

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
