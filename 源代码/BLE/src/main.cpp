#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <ICM42688.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

static const char *BLE_DEVICE_NAME = "IMU-MOTION-01";
static const char *BLE_SERVICE_UUID = "7d2a0001-6c8a-4f6b-9c65-4f4d55494d55";
static const char *BLE_NOTIFY_UUID = "7d2a0002-6c8a-4f6b-9c65-4f4d55494d55";
static BLECharacteristic *bleDataCharacteristic = nullptr;
static bool bleConnected = false;

class ImuServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { bleConnected = true; }
  void onDisconnect(BLEServer *server) override {
    bleConnected = false;
    server->startAdvertising();
  }
};

void setupBle() {
  BLEDevice::init(BLE_DEVICE_NAME);
  BLEDevice::setMTU(185);
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ImuServerCallbacks());
  BLEService *service = server->createService(BLE_SERVICE_UUID);
  bleDataCharacteristic = service->createCharacteristic(
      BLE_NOTIFY_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  bleDataCharacteristic->addDescriptor(new BLE2902());
  service->start();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(BLE_SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("[BLE] IMU-MOTION-01 advertising");
}

void notifyBleLine(const char *line) {
  if (!bleConnected || bleDataCharacteristic == nullptr) return;
  const size_t length = strlen(line);
  const size_t chunkSize = 20;
  for (size_t offset = 0; offset < length; offset += chunkSize) {
    size_t count = min(chunkSize, length - offset);
    bleDataCharacteristic->setValue((uint8_t *)(line + offset), count);
    bleDataCharacteristic->notify();
  }
}

// ================================================================
// 硬件连接说明（依据原理图网表 Netlist_Schematic1_2026-08-26.tel 推导）
//
//  ICM-42688-P (U10)  —— SPI 从机
//    IMU_INTERUPT : ESP32-S3 GPIO9  (模块引脚13) -> U10.4  INT1  (可选)
//    IMU_/SS      : ESP32-S3 GPIO10 (模块引脚14) -> U10.12 CS
//    IMU_MOSI     : ESP32-S3 GPIO11 (模块引脚15) -> U10.14 SDI
//    IMU_SCK      : ESP32-S3 GPIO12 (模块引脚16) -> U10.13 SCLK
//    IMU_MISO     : ESP32-S3 GPIO13 (模块引脚17) -> U10.1  SDO
//
//  LIS2MDLTR (U2) —— I2C 从机（器件地址 0x1E）
//    SCL        : ESP32-S3 GPIO33 (模块引脚28) -> U2.1 SCL/SPC
//    SDA        : ESP32-S3 GPIO34 (模块引脚29) -> U2.4 SDA/SDI/SDO
//    INT/DRDY   : ESP32-S3 GPIO47 (模块引脚27) -> U2.7 INT/DRDY (可选)
// ================================================================

// ---- ICM-42688-P SPI 引脚 ----
#define PIN_ICM_CS    10
#define PIN_ICM_SCK   12
#define PIN_ICM_MOSI  11
#define PIN_ICM_MISO  13
#define PIN_ICM_INT   9

// ---- LIS2MDLTR I2C 引脚 ----
#define PIN_LIS_SDA   34
#define PIN_LIS_SCL   33
#define PIN_LIS_DRDY  47

// ---- LIS2MDLTR 寄存器 ----
#define LIS2MDL_ADDR        0x1E
#define LIS2MDL_WHO_AM_I_REG  0x4F
#define LIS2MDL_CFG_A         0x60
#define LIS2MDL_CFG_B         0x61
#define LIS2MDL_CFG_C         0x62
#define LIS2MDL_OUTX_L_REG    0x68
#define LIS2MDL_WHO_AM_I_VAL  0x40

// ICM-42688 SPI 对象（构造时指定 CS 引脚）
ICM42688 icm(SPI, PIN_ICM_CS);

// ---------- LIS2MDLTR 底层 I2C 读写 ----------
bool lis2mdlWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(LIS2MDL_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

uint8_t lis2mdlRead(uint8_t reg) {
  Wire.beginTransmission(LIS2MDL_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return 0xFF;
  if (Wire.requestFrom((uint8_t)LIS2MDL_ADDR, (uint8_t)1) != 1) return 0xFF;
  return Wire.read();
}

bool lis2mdlReadData(int16_t &mx, int16_t &my, int16_t &mz, int16_t &mt) {
  Wire.beginTransmission(LIS2MDL_ADDR);
  Wire.write(LIS2MDL_OUTX_L_REG);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)LIS2MDL_ADDR, (uint8_t)8) != 8) return false;
  uint8_t buf[8];
  for (uint8_t i = 0; i < 8; i++) buf[i] = Wire.read();
  mx = (int16_t)((buf[1] << 8) | buf[0]);
  my = (int16_t)((buf[3] << 8) | buf[2]);
  mz = (int16_t)((buf[5] << 8) | buf[4]);
  mt = (int16_t)((buf[7] << 8) | buf[6]);
  return true;
}

bool lis2mdlSetup() {
  delay(50);
  if (lis2mdlRead(LIS2MDL_WHO_AM_I_REG) != LIS2MDL_WHO_AM_I_VAL) return false;
  // CFG_REG_A(0x60) = 0x8C:
  //   COMP_TEMP_EN=1(温度补偿), ODR[1:0]=11(100Hz), MD[1:0]=00(连续模式)
  if (!lis2mdlWrite(LIS2MDL_CFG_A, 0x8C)) return false;
  // CFG_REG_B(0x61) = 0x02: 启用偏移消除 OFF_CANC
  if (!lis2mdlWrite(LIS2MDL_CFG_B, 0x02)) return false;
  // CFG_REG_C(0x62) = 0x11: BDU=1(数据块更新) + DRDY_on_PIN=1
  if (!lis2mdlWrite(LIS2MDL_CFG_C, 0x11)) return false;
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  setupBle();

  Serial.println("==============================================");
  Serial.println("  IMU 数据读取 : ICM-42688-P (SPI) + LIS2MDLTR (I2C)");
  Serial.println("==============================================");

  // ---- SPI 总线（自定义引脚）----
  SPI.begin(PIN_ICM_SCK, PIN_ICM_MISO, PIN_ICM_MOSI, PIN_ICM_CS);

  // ---- 初始化 ICM-42688-P ----
  int st = icm.begin();
  if (st > 0) {
    icm.setAccelFS(ICM42688::gpm8);     // 加速度量程 ±8 g
    icm.setGyroFS(ICM42688::dps2000);   // 陀螺仪量程 ±2000 °/s
    Serial.println("[ICM-42688] 初始化成功 (WHO_AM_I = 0x47)");
  } else {
    Serial.printf("[ICM-42688] 初始化失败, 错误码 %d (请检查 SPI 接线)\r\n", st);
  }

  // ---- 初始化 LIS2MDLTR ----
  Wire.begin(PIN_LIS_SDA, PIN_LIS_SCL);
  Wire.setClock(400000);
  if (lis2mdlSetup()) {
    Serial.println("[LIS2MDL]   初始化成功 (WHO_AM_I = 0x40)");
  } else {
    Serial.println("[LIS2MDL]   初始化失败 (请检查 I2C 接线 / CS 引脚电平)");
  }

  Serial.println();
  Serial.println("数据格式 (CSV):");
  Serial.println("AccX(g),AccY(g),AccZ(g),GyrX(dps),GyrY(dps),GyrZ(dps),ICM温度(C),MagX(mG),MagY(mG),MagZ(mG),LIS温度(raw)");
}

void loop() {
  // ---- 读取 ICM-42688-P ----
  float ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0, t = 0;
  if (icm.getAGT() > 0) {
    ax = icm.accX(); ay = icm.accY(); az = icm.accZ();
    gx = icm.gyrX(); gy = icm.gyrY(); gz = icm.gyrZ();
    t  = icm.temp();
  }

  // ---- 读取 LIS2MDLTR ----
  int16_t mx = 0, my = 0, mz = 0, mt = 0;
  bool magOk = lis2mdlReadData(mx, my, mz, mt);

  // ---- 串口输出 ----
  char line[256];
  if (magOk) {
    // 磁力计灵敏度 1.5 mgauss/LSB
    snprintf(line, sizeof(line),
             "%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.2f,%.1f,%.1f,%.1f,%d\n",
             ax, ay, az, gx, gy, gz, t, mx * 1.5f, my * 1.5f, mz * 1.5f, mt);
  } else {
    snprintf(line, sizeof(line),
             "%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.2f,0.0,0.0,0.0,0\n",
             ax, ay, az, gx, gy, gz, t);
  }
  Serial.print(line);
  notifyBleLine(line);

  delay(50);   // 约 20 Hz
}
