# 鑫煜量化交易系统

在本机浏览器运行的美股研究工具。交易图表在同一窗口展示 K 线、成交量、KDJ、MACD，以及日线和周线的多空共振。金色 ▲ 在下影线末端，红色 ▼ 在上影线末端。实心代表强共振，空心代表中档共振。

系统支持分类自选、研究计划和日志、3570 / 3221 仓位评估、海龟 55/20 历史回测，以及基本面和宏观观察。共振标记与海龟回测使用不同规则版本。

## Windows 和 macOS 快速开始

1. 安装 [Python 3.12](https://www.python.org/downloads/)。Windows 可选中安装程序中的 Python Launcher 或 Add Python to PATH。
2. 下载源码 ZIP 并解压，或用 Git 克隆本项目。
3. Windows 双击 `start-windows.cmd`。macOS 可打开终端进入项目文件夹，运行 `zsh start-mac.command`。
4. 首次启动会创建 `.venv` 并安装依赖。默认浏览器打开后即可使用。关闭启动终端或按 Ctrl+C 可停止服务。

首次安装依赖需要联网。默认用程序生成的**合成演示行情**，界面会标注「演示行情」。在演示模式可查看日、周、月线并试用本地研究功能。分时、SEC 基本面和黄金宏观查询需要联网模式。

也可直接从终端启动：

```powershell
# Windows
py -3.12 start.py
py -3.12 start.py --live
```

```bash
# macOS
python3.12 start.py
python3.12 start.py --live
```

`--live` 启用原系统的行情供应商和公开数据接口。可参考 `.env.example` 设置自己有权限使用的行情凭证。供应商的可用性、数据延迟和复权方式以界面提示为准。联网模式仅用于本机研究，向他人展示或转发行情需遵循供应商条款。

## 数据位置

- Windows 使用 `%LOCALAPPDATA%\XinyuQuantOpen`。
- macOS 使用 `~/Library/Application Support/XinyuQuantOpen`。
- 两种模式分别使用 `demo` 和 `live` 数据目录。用户可用 `--data-dir` 指定其它目录。
- 自选和研究计划可从「研究与工具 → 数据服务」导出。日线和周线各自计算指标，周线点位使用交易所日历确认全周数据。

服务只监听 `127.0.0.1`。程序在个人设备上运行，暂无多人登录，部署到公网前应另行实现用户鉴权和数据隔离。

## 开发与验证

安装开发依赖并构建前端后运行测试：

```bash
python -m pip install -r requirements-test.txt
python frontend/build.py
python -m unittest discover -s tests -p 'test_*.py'
```

`start.py` 会管理虚拟环境，`run.py` 可在已安装依赖的环境中直接运行。应用源码由 Python 后端、HTML/CSS/JavaScript 前端及 SQLite 数据层构成。GitHub Actions 在 Windows 和 macOS 上运行单元测试与本地应用启动检查。

本仓库提供跨平台源码和本地浏览器入口。Mac 桌面应用及 Windows 安装包是单独的打包工作。开源许可见 [LICENSE](LICENSE)。第三方数据及外链素材遵循原著作权或服务条款。
