# v0.3.0 原生Python标准入口

标准场景用GTK3 DrawingArea+Cairo绘制，不使用WebKit、浏览器或HTTP服务器。HA适配器同进程由后台线程执行，保持绘图和触摸不被网络阻塞。旧网页预览单独保留，不是当前运行架构。

## 标准命令

```bash
./app --version
./app info --json
./app check --port 2 --shape round --panels 1 --input touch
./app start --port 2 --shape round --panels 1 --input touch --data-source demo
./app status --port 2
./app logs --port 2 --follow
./app restart --port 2
./app stop --port 2
```

run使用相同参数前台调试，与start二选一；--port取1/2，round、1 panel、touch、climate是当前唯一profile。其他形状、无触摸、双面板、layout/content请求明确拒绝。--data-source默认demo，--config相对调用目录。

check只读检查配置、当前桌面、依赖、模式/画布、占用；不控制HA设备、不改时序。启动就绪需原生画面实际绘制、数据获取成功并确认surface处于目标monitor。定时检查模式/位置，失联后报告错误并退出，不自动改硬件。屏幕短暂断开也可能触发此行为；重新接好后start或restart。

## 依赖和安装

```bash
./setup.sh --install-only
```

安装器仅在缺包时APT安装python3、python3-gi、python3-gi-cairo、python3-cairo、gir1.2-gtk-3.0、gir1.2-gtklayershell-0.1、wlr-randr。全部已有则不联网下载，不需要pip/Node/编译/虚拟环境。无参数也只安装，不会自动打开旧浏览器。旧网页工作流另用--legacy-browser。

运行以普通桌面用户执行。Linux入口使用/usr/bin/python3读取发行版GTK绑定。Wayland桌面须已登录；SSH自动寻找同用户唯一socket，多个会话需明确WAYLAND_DISPLAY。目标Bookworm/labwc，缩放100%、输出不旋转、方形画布>=360。

## 触摸与配置

绘图和命中测试共用480单位局部坐标，按实际圆形安全区缩放，safe_inset_percent为0～10，默认3。按钮/环形拖动、单指归属、取消和按钮外抬起由touch.py处理；原生touch消费后不再重复按鼠标提交。pointer计数可能包含模拟触摸。

room、safe_inset_percent与homeassistant配置见examples。demo不读取HA_*环境，live必须有明确url、实体和私有token_file。令牌由当前用户0600文件读取，不存命令、状态或日志。失败反馈离线/未保存，不变为demo。

同一数据工作线程串行处理读写，避免写入次序颠倒。快速连续操作在提交前短暂合并；网络已提交的操作不会因之后取消另一手势自动撤回。只读模式未声明，不将--input none当作禁用API的办法。

## 监督与归属

flock按用户/HDMI口租约，私有UNIX控制socket核对app与instance。run/start互斥，重复相同参数/配置启动幂等，stop只清理本实例。不会killall、修改显示、注销桌面。已退出测试进程留下的无人监听socket不算占用，文件也不擅自删除。

日志位于用户XDG_STATE_HOME（默认~/.local/state）下screen-app应用目录；运行记录位于XDG_RUNTIME_DIR。正常图形桌面会话期间，后台start不依赖SSH终端存活；重启/桌面退出后的恢复不承诺。没有新开机自启动。

--replace仅替换本项目同版本实例，新启动失败尝试原配置引用恢复，外部配置变动/真实设备动作不能回退。不同运行版本或其他项目owner先正常停止，不强杀。内部run --context私有JSON仍走同一profile和配置校验。

0成功；2参数；3能力/输出；4占用/归属；5依赖/会话；6配置/版本；7启动/健康；8缺live配置。查询JSON，run生命周期和日志跟随按行JSON。

## 完整部署与验收

[中文SSH指南](raspberry-pi-ssh.md) · [English SSH guide](raspberry-pi-ssh_EN.md) · [实测记录](verification.md)。本项目不强依赖旧显示设置工具。800×800圆形触摸演示已由用户确认，其他尺寸、HA实机控制和长期运行需各自验证。
