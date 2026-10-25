# v0.3.0 验证记录

## 已实际验证的配置

- 日期：2026-10-25。
- 系统：树莓派aarch64，Debian/Raspberry Pi OS Bookworm，labwc/Wayland桌面。
- 输出：HDMI-A-2，800×800、60Hz，缩放1，normal transform。
- 界面：Python/GTK3/Cairo原生单圆触摸看板；无WebKit、浏览器或HTTP服务。
- 依赖：目标机原有Python GTK/Cairo/layer-shell及wlr-randr即可，未完成也未继续WebKit下载。
- 启动：标准./app check和start成功，surface/viewport定位确认，demo健康正常。
- 用户反馈：画面完整，按钮和旋钮都正常。
- 系统证据：观察到10次原生touch begin，pointer计数0，目标温度随操作改变。

只代表本次配置和用户观察，不将EDID名称当成产品SKU，也不保证其他尺寸、设备、双屏、live HA和长期稳定性。用户确认后的一次状态检查观察到HDMI短暂不在输出列表，按设计退出并报告断开；输出重新存在后已按相同参数重新启动。该事件不归因于触摸或时序修复，后续仍需观察连接稳定性。

## 软件检查

Mac与目标Pi均通过27项标准库测试；360/480/720/800的原生Cairo绘图也在Pi上执行成功。标准库测试覆盖命令能力、demo/live隔离、HA测试服务、配置权限、连接器几何、租约/控制归属、幂等/替换回退和原生手势。绘图与触摸共用局部坐标，在360/480/720/800及不同安全边距检查变换一致性。

原ui目录的浏览器检查仅对应保留网页版本，不作为v0.3.0原生界面的验证证据。
