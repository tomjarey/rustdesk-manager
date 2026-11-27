# rustdesk-manager — 个性化控制端（管理端）编译仓库

本仓库是 [rustdesk/rustdesk](https://github.com/rustdesk/rustdesk) 的源码镜像，基线 **1.5.3**（源码 `95cca3f661f635b3cc85c04935fe8d96d8f432ef`，`libs/hbb_common` `fae47e024dd83cef6aaecde0aa7d11731df11649`）。

用途只有一个：编译 **控制端（manager / controller）** 的 Windows x64 安装包与单文件 EXE，与被控端仓库（`tomjarey/rustdesk`，`hntom-incoming` 系列）分开，互不覆盖 Release。

## 定制内容

| 维度 | 值 |
| --- | --- |
| ID / 中继服务器 | `hntom.cn`（编译期写入 `OVERWRITE_SETTINGS`，用户不可改） |
| 服务器公钥 | `RhWHCrir6gLBCZtX8BTdoT04nn+yfAzbh5Fi2SKFtW0=` |
| API 服务器 | `https://hntom.cn:21114/client`（`/client` 保留；`allow-https-21114=Y`） |
| 网络设置页 | 隐藏整页（`hide-network-settings=Y`，`BUILTIN_SETTINGS`） |
| 默认编码器 | `av1`（`UserDefaultConfig` 的 `codec_preference` 默认值） |
| 默认图像质量 | `best`（即“画质最优化”，`image_quality` 默认值） |
| 分辨率菜单 | 连接后远端工具条的“分辨率”子菜单强制常显，支持原始 / 适应本地窗口 / 自定义宽高 / 枚举列表 |
| 连接模式 | 完整客户端（`HARD_SETTINGS` 保持默认，**不是** incoming-only） |
| 打印驱动 | 不打包 |
| 签名 | 不签名，Release 标记 prerelease |

`HARD_SETTINGS` 刻意不写入 `conn-type=incoming`：控制端必须能主动发起连接。

## 文件

- `.github/workflows/hntom-manager.yml` — 三作业流水线（bridge / topmost / windows），产出 MSI + 单文件 EXE + 定制源码 + 补丁 + 校验文件
- `.github/hntom/patch_manager.py` — 服务器预置、网络页隐藏、AV1 与画质最优默认值（`SHA256 458875b5ffadab9ac915f5735cfa7b329b5cf93dc8e7199bca41212d2a8c6bfe`）
- `.github/hntom/patch_resolution.py` — 分辨率菜单强制显示 + Windows 显示器名回退（`SHA256 bc3e293e086717cd303d11671d2ad43fa2f5a09f31570f9adfbcfe43e1c3f0e6`，与被控端仓库同一份）
- `.github/workflows-upstream/` — 上游工作流原样存档，挪出 `workflows/` 目录以免在本仓库触发上游 CI

## 触发

Actions → **HNTOM Manager Windows x64** → Run workflow，或修改 `.github/workflows/hntom-manager.yml` 推送到 `master`。

产物：

```
rustdesk-manager-1.5.3-windows-x64.msi              # 安装包
rustdesk-1.5.3-hntom-manager-windows-x64.exe        # 单文件免安装
rustdesk-1.5.3-hntom-manager-source.tar.gz
hntom-config.patch / hntom-resolution.patch
hntom-manager.py / hntom-resolution.py
BUILD-INFO.txt / GIT-SUBMODULES.txt / EXTERNAL-ASSETS-SHA256.txt / PAYLOAD-SHA256.txt / SHA256SUMS.txt
```

## 与上游的差异

仅三处，且全部编译期打补丁、构建期用 `grep` 与 `sha256sum -c` 双重校验：

1. `libs/hbb_common/src/config.rs`：`OVERWRITE_SETTINGS`、`BUILTIN_SETTINGS` 与 `UserDefaultConfig::get` 的两个默认值。
2. `flutter/lib/desktop/widgets/remote_toolbar.dart`：八处分辨率菜单可见性/交互改动。
3. `src/platform/windows.rs`：`resolve_device_name()` 回退 `\\.\DISPLAY1..8`。

其余（含打印驱动相关代码、CLI、TLS 校验）保持上游原样。许可证遵循上游 AGPL-3.0。
