> **运行位置**：本文命令在代码仓库的 `源代码/WIFI/` 中执行，说明文件所在文件夹不是程序目录。

# 上位机使用：查看、记录与导出

## 启动

```powershell
python -m pip install -r requirements.txt
python run_dashboard.py
```

浏览器打开 <http://127.0.0.1:8000>，按[连接步骤](WIFI_README.md)选择通信方式并连接设备。使用 USB 时，请先关闭占用串口的监视器。

## 当前数据映射

- 当前 11 列 CSV 数据映射到“右腕”。
- 其余 13 个节点显示为静止模拟状态。
- 每次记录在 `recordings/imu-日期-时间/` 生成三个 UTF-8 BOM CSV：
  - `imu-data.csv`：14 节点姿态与传感器数据；
  - `body-trajectory.csv`：骨盆中心短时趋势估算；
  - `node-trajectory.csv`：所选节点的骨骼约束相对轨迹。
- CSV 中文表头可由 Excel 直接打开。人体整体轨迹不是绝对定位结果。
- 接收质量采用最近 2 秒窗口计算速率；当前无包序号，因此丢包率为基于 20 Hz 到达间隔的估算值。
- 网页顶部“预览记录”可查看会话元数据和 CSV 前 100 行；“导出记录”会将三个 CSV 打包为 ZIP 下载。正在写入的会话需停止记录后才能导出。

## 测试

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
```

协议变化时，优先新增或替换 `dashboard/protocol.py` 中的适配器，不改变页面使用的标准节点消息。
