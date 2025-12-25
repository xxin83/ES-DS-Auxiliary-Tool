# ES-DE Toolkit (ES-DE 配置工具箱)

这是一个专为 **ES-DE (EmulationStation Desktop Edition)** 开发的现代化配置工具箱。项目采用 Python 和 `customtkinter` 构建，具备高度灵活的插件化架构，旨在简化 ES-DE 的复杂配置流程。

## 🚀 核心特性

- **插件化框架**：通过 `BaseInterface` 和 `interface_loader` 实现功能解耦，可轻松添加自定义模块。
- **现代化 UI**：基于 `customtkinter` 库开发，支持原生深色模式，界面友好。
- **系统编辑器**：可视化编辑 `es_systems.xml`，支持自动备份与跨平台路径适配。
- **配置同步**：集中管理 ES-DE 根目录、ROM 目录及系统清单路径。
- **便捷操作**：支持全局快捷键（如 `Ctrl+S` 快速保存），具备自动补全和路径检测功能。

## 🛠️ 技术栈

- **语言**: Python 3.8+
- **UI 框架**: CustomTkinter
- **数据格式**: XML, JSON

## 📂 项目结构

```text
.
├── window_shell.py           # 程序主入口，负责框架绘制与插件调度
├── base_interface.py         # 插件抽象基类，定义标准接口
├── interface_loader.py       # 插件自动注册与加载机制
├── config_settings_plugin.py  # [插件] 基础路径与全局设置管理
└── systems_editor_plugin.py  # [插件] es_systems.xml 可视化编辑器
📦 安装与运行
环境准备： 确保您的系统已安装 Python 3.8 或以上版本。

安装依赖：

Bash

pip install customtkinter
启动程序：

Bash

python window_shell.py
🧩 插件开发
您可以快速开发并集成自己的功能模块：

创建新 Python 文件并继承 BaseInterface。

实现必要的方法：get_title() (显示名称), get_order() (排序), create_ui() (界面逻辑)。

在文件末尾调用 register_interface 即可自动出现在主程序的导航栏中。

📝 开发规范
界面语言：UI 提示及交互均使用中文。

版本控制：版本号遵循 0.0.x 格式，日常调整仅修改最后一位数字。

代码风格：保持代码简洁，避免增加不必要的冗余注释。

⚖️ 许可
MIT License
