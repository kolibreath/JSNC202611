# 设备初始化 Checklist（每台设备一份，完成后归档到本目录）

> 对应设计文档 4.4.1。两台设备分别建档：`mid.md`（中端主力）/ `flagship.md`（旗舰对照）。

## 基础信息（D1 填写）

| 项 | 中端机（mid） | 旗舰机（flagship） |
|---|---|---|
| 型号 | 待采购（8GB RAM，骁龙 8s Gen3/天玑 8300 档） | 待采购（12GB+，骁龙 8 Elite 档） |
| Android 版本 | | |
| RAM/存储 | | |
| SoC | | |

## 初始化步骤（D1 执行）

- [ ] 开发者选项 + USB 调试开启；`adb devices` 可见
- [ ] 关闭系统自动更新
- [ ] 关闭电池优化/后台冻结对本项目进程的影响（设置白名单）
- [ ] 固定屏幕亮度；关闭省电模式
- [ ] 安装 MNN-Chat APK（仅演示用，不承担评测）
- [ ] 探测温度节点：`adb shell "cat /sys/class/thermal/thermal_zone*/type"` 与 `.../temp`，
      记录 CPU 对应的 zone 编号 →（填入下行）
  - CPU 温度节点：mid = `/sys/class/thermal/thermal_zone____/temp`
- [ ] 记录 dumpsys 可用性：`dumpsys meminfo` / `dumpsys batterystats` / `dumpsys thermalsy`(如有)

## 测量前基线（每次正式测量执行）

- [ ] 静置降温至初始温度 ±1°C（记录基线温度）
- [ ] 电量 50–80%，插电状态全程统一（建议不插电）
- [ ] 清理后台（`adb shell am kill-all` 或重启后仅保留必要进程）
- [ ] 飞行模式开关状态与当次 run_id 一起记录（飞行模式 = 正式口径）
