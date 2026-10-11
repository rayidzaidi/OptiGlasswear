#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// =====================================================================
// 1. SET YOUR WI-FI CREDENTIALS HERE
// Recommendation: Use your phone's Hotspot (with a simple name, no apostrophes)
// =====================================================================
const char* ssid = "Galaxy A14 64AB";
const char* password = "sd290322";

// =====================================================================
// 2. CAMERA PIN DEFINITION (AI THINKER ESP32-CAM)
// =====================================================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

WebServer server(80);

// Handler to serve the /cam-hi.jpg image frame
void handle_cam_hi() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  WiFiClient client = server.client();
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: image/jpeg\r\n";
  response += "Content-Length: " + String(fb->len) + "\r\n";
  response += "Access-Control-Allow-Origin: *\r\n\r\n";
  server.sendContent(response);
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

void handle_root() {
  server.send(200, "text/html",
    "<html><head><title>ESP32-CAM</title></head><body>"
    "<h2>ESP32-CAM Server is Online!</h2>"
    "<p><a href='/cam-hi.jpg'>Click here to view /cam-hi.jpg</a></p>"
    "<img src='/cam-hi.jpg' width='480'/>"
    "</body></html>"
  );
}

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("--- Starting ESP32-CAM ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA; // 640x480 for fast streaming
    config.jpeg_quality = 12;
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA; // 320x240
    config.jpeg_quality = 14;
    config.fb_count = 1;
  }

  // Initialize Camera
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  // Connect to Wi-Fi
  Serial.print("Connecting to: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("=================================================");
  Serial.println("WiFi Connected Successfully!");
  Serial.print("Camera URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/cam-hi.jpg");
  Serial.println("=================================================");

  // Set URL routes
  server.on("/", handle_root);
  server.on("/cam-hi.jpg", handle_cam_hi);
  server.on("/capture", handle_cam_hi);

  server.begin();
  Serial.println("HTTP Server started.");
}

void loop() {
  server.handleClient();
}
