# 将圆形触摸看板部署到树莓派，通过SSH运行

本指南可单独使用，不需要application总仓库或pi-setting。项目文件是复制到树莓派的用户目录，**不是重新烧录TF卡系统**。

[English](raspberry-pi-ssh_EN.md) · [项目说明](../README_CN.md)

## 1. 准备与执行位置

树莓派已通过TF卡启动Raspberry Pi OS Bookworm 64位桌面，联网并开启SSH，当前用户已登录labwc/Wayland桌面。仅有SSH或控制台登录不足以显示图形程序。

屏幕应先稳定显示：方形画布至少360×360、100%缩放、输出不旋转。触摸USB数据线已连接并正确映射；显示配置可用系统或厂家方法完成，不要求安装screen-config/screen-test。v0.3.0已在一套800×800圆形触摸配置验证，其他配置仍需实测。

| 命令位置 | 用途 |
| --- | --- |
| Mac本机终端 | 把本地项目复制到Pi、建立SSH连接 |
| Pi的SSH终端 | 安装依赖、检查和运行应用、日志与停止 |

下面用pi@raspberrypi.local作为示例，**替换为自己的Pi用户名与主机名/IP**，不表示所有系统默认用户都叫pi。首次SSH连接应核对主机指纹，按本机提示认证；文档不保存密码。

## 2. Mac：复制本地项目

在Mac进入包含round-screen-homeassistant-kiosk文件夹的父目录，例如已下载或本地修改代码所在目录：

```bash
ssh pi@raspberrypi.local 'mkdir -p ~/apps/round-screen-homeassistant-kiosk'
rsync -av --exclude=.git --exclude=.venv --exclude=__pycache__ --exclude=secrets --exclude=ha-token round-screen-homeassistant-kiosk/ pi@raspberrypi.local:~/apps/round-screen-homeassistant-kiosk/
```

源目录结尾的/表示复制目录内容。必须复制整个项目，包括app、orbit_app和screen-app.json；完整复制也保留旧网页兼容文件；仅复制网页不能运行标准命令。私有HA配置建议放在Pi的~/.config/orbit，不随项目发布。

本地改造尚未推送时，使用此复制方式；git clone/pull只能取得GitHub已经发布的内容。

若选择GitHub获取方式，先在Pi SSH终端执行下面步骤；不要在已完成rsync的同名目录再次clone：

```bash
sudo apt-get update
sudo apt-get install -y git
mkdir -p ~/apps
git clone https://github.com/tekgroaml/round-screen-homeassistant-kiosk.git ~/apps/round-screen-homeassistant-kiosk
```

## 3. Pi：通过SSH安装

以下ssh命令仍在Mac执行：

```bash
ssh pi@raspberrypi.local
```

出现Pi的命令提示符后，下面均在这个SSH终端执行：

```bash
cd ~/apps/round-screen-homeassistant-kiosk
chmod +x app setup.sh scripts/*.sh
./setup.sh --install-only
./app --version
./app info --json
```

只首次或依赖有变化时需要安装。安装器会请求sudo进行APT安装，必须能访问软件源；app运行命令不要加sudo。--install-only明确只安装原生依赖；新版默认也不自动打开程序。

如果项目已经发布到GitHub，也可在Pi上安装git后，将仓库克隆到目标目录，作为第2步的替代：`git clone https://github.com/tekgroaml/round-screen-homeassistant-kiosk.git ~/apps/round-screen-homeassistant-kiosk`。仅在目标目录不存在时克隆；已有副本不要重复覆盖克隆，安装与运行步骤相同。

## 4. Pi：预检与后台启动

```bash
./app check --port 1 --shape round --panels 1 --input touch
./app start --port 1 --shape round --panels 1 --input touch --data-source demo
```

port1=HDMI-A-1（Pi4板子HDMI0，靠近USB-C），port2=HDMI-A-2（板子HDMI1）。连接第二个接口时将命令中的--port统一改为2；不跟随桌面左右位置重新编号。

check只检查配置、依赖、会话、输出和占用。start会等待页面及输出定位就绪后返回；失败时不假装启动成功。默认demo无需HA服务器，不会使用遗留HA环境变量控制设备。

入口自动寻找**当前用户**的唯一Wayland会话。不需要填写DISPLAY，也不使用ssh -X。多会话时在Pi先列出真实socket：

```bash
python3 - <<'PY'
import os
from pathlib import Path
for item in sorted((Path('/run/user') / str(os.getuid())).glob('wayland-*')):
    if item.is_socket():
        print(item.name)
PY
```

如输出多个，确认哪一个是目标桌面，再使用例如`export WAYLAND_DISPLAY=wayland-0`（替换成实际名称）。无socket时先登录Pi桌面，不要随意猜会话名或通过重启桌面掩盖问题。

## 5. Pi：状态、日志、重启、停止

### 先手动测试颜色和触摸，再切换到演示

如果你已经安装可选的screen-test工具，可在同一个SSH终端依次执行。下面按800×800圆屏接接口2举例；接接口1时将所有编号统一改成1：

```bash
cd ~/apps/round-screen-homeassistant-kiosk
# 如果演示原来在运行，先停止；未运行时也可执行
./app stop --port 2
screen-test tap-cycle --screen 2
```

现在用手指点击实体屏幕，确认颜色切换。观察完成后再执行下一段，不要两段一起粘贴跳过手动测试：

```bash
screen-test stop --screen 2
./app start --port 2 --shape round --panels 1 --input touch --data-source demo
./app status --port 2
```

切换时先停止当前程序，避免两个窗口占同一输出。screen-test只是已有工具的可选流程；本应用不要求安装它。

### 日常管理

```bash
./app status --port 1
./app logs --port 1 --follow
```

在日志命令中按Ctrl+C只是退出日志跟随，应用继续运行。返回提示符后可执行：

```bash
./app restart --port 1
./app stop --port 1
```

start是受监督的后台启动，**SSH断开后仍继续运行，前提是Pi的图形桌面会话保持登录**。再次SSH登录后进入同一目录即可查询或停止。Pi重启/桌面退出后不承诺自动恢复；本版没有自动安装新的开机启动。

需要前台调试时先stop，再将同一启动参数用于./app run；Ctrl+C结束前台调试。不要把run当作断开SSH后持续运行的方式，也不要killall chromium。

## 6. 更新本地修改

先在Pi执行./app stop --port 1，然后回Mac重复第2步的rsync，再通过SSH进入项目。若依赖有变化，执行./setup.sh --install-only，然后：

```bash
./app --version
./app check --port 1 --shape round --panels 1 --input touch
./app start --port 1 --shape round --panels 1 --input touch --data-source demo
```

以--version核对实际复制版本，不只看Mac的源目录。已在运行的旧版本应先停止，不在运行中替换代码后声称回退旧二进制。若使用git副本，确认远端已发布、工作区无需要保留的冲突修改后再更新；本地复制路径与git路径选一种维护方式。

## 7. 常见问题与真实数据

| 现象 | 检查 |
| --- | --- |
| SSH能连但check提示没有桌面 | Pi是否登录同一用户的Wayland桌面，是否只是控制台/登录界面 |
| 缺少Python GTK/Cairo/wlr-randr | 在Pi执行安装步骤，标准入口目标是Bookworm/labwc，不是Mac/X11 |
| 输出或画布不支持 | 先在系统/厂家工具中配置正确模式、100%缩放及不旋转 |
| Permission denied | 确认目录归当前用户，执行chmod步骤；不要改用sudo启动 |
| 旧kiosk服务占用 | 先用./scripts/install_service.sh --uninstall迁移旧入口，私有环境文件保留 |
| screen-test占用 | 若已安装该可选工具，先正常停止对应口测试 |
| 有画面但触摸偏移/串屏 | USB控制器映射与坐标需单独验证，应用不自动校准 |
| touch_events为0 | 也检查pointer_events；鼠标模拟触摸可能归为pointer，计数不证明位置正确 |

连接真实Home Assistant的私有配置、token_file权限和live命令见[项目README](../README_CN.md#连接真实home-assistant)。先完成demo实测，再明确启用live；缺配置或离线不会静默切回模拟。
