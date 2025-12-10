import customtkinter as ctk
from tkinter import messagebox
from typing import Optional, Dict, List, Type
import sys

from interface_loader import get_available_interfaces
from base_interface import BaseInterface

# --- 全局常量 (仅用于显示) ---
__version__ = "1.0 @爱折腾的老家伙"

# --- 主程序类 (Shell) ---
class WindowShell(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title(f"配置工具 (v{__version__})")
        self.geometry("1280x720")
        self.bind("<Control-s>", lambda e: self._handle_ctrl_s())

        self.current_component: Optional[BaseInterface] = None
        self.interface_instances: Dict[str, BaseInterface] = {}
        
        # --- 设置布局 ---
        self.grid_rowconfigure(0, weight=1) 
        self.grid_columnconfigure(1, weight=1)
        
        self._create_navigation_frame()
        self._create_main_content_frame()
        
        self._load_plugins()
        self._show_initial_interface()
        
    def _handle_ctrl_s(self):
        """调用当前界面的保存方法。"""
        if self.current_component and hasattr(self.current_component, 'save_config'):
            self.current_component.save_config()
        else:
            messagebox.showinfo("提示", "当前界面没有可保存的配置。")

    # --- 新增方法: 显示说明信息 ---
    def _show_about_dialog(self):
        """显示关于工具的详细说明和免责声明。"""
        
        # 使用精炼后的中文文本
        about_text = """
本配置工具的设计宗旨是简化您的游戏元数据管理流程，我们竭诚为您提供高效便捷的配置服务。

**核心技术与数据源：**
1. 数据库整合：本工具数据库源自**RetroArch**生态系统的精心整合，确保了数据源的广泛与权威性。
2. 刮削原理：在刮削过程中，程序将精确读取您ROM文件的**哈希值**（如CRC、MD5、SHA1），并通过与知名游戏数据库 **TheGamesDB** 提供的海量数据进行智能比对与搜索，以提供准确的元数据匹配。

**重要声明与使用建议：**
1. 数据备份：鉴于配置修改可能涉及系统文件的变动，我们强烈建议您在操作过程中**随时备份重要数据**。
2. 免责条款：**本软件不对因使用本工具而导致的任何系统配置或数据损失承担任何直接或间接的责任。用户需自行承担使用风险。**

**致谢：GitHub上的各个开源库**
本项目由（爱折腾的老家伙）与 **Gemini AI**（人工智障）携手合作，共同折腾完成，旨在为玩家提供便捷的配置管理体验。
        """
        messagebox.showinfo("工具说明与免责声明", about_text.strip())

    def _create_navigation_frame(self):
        """创建左侧导航框架和功能按钮。"""
        self.navigation_frame = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.navigation_frame, text="功能列表", 
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(15, 5))
        
        # --- 新增: 工具说明按钮 ---
        ctk.CTkButton(self.navigation_frame, text="工具说明", 
                      command=self._show_about_dialog).pack(fill="x", padx=10, pady=(0, 10))

        self.nav_button_frame = ctk.CTkFrame(self.navigation_frame, fg_color="transparent")
        self.nav_button_frame.pack(fill="x", padx=10, pady=5, expand=True) 
        
        ctk.CTkLabel(self.navigation_frame, text=f"版本: v{__version__}").pack(side="bottom", anchor="sw", padx=10, pady=5)


    def _create_main_content_frame(self):
        """创建右侧主内容区，用于加载插件界面。"""
        self.main_content_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_content_frame.grid(row=0, column=1, sticky="nsew")
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)
        
    def _load_plugins(self):
        """动态加载所有已注册的插件并创建导航按钮。"""
        available_interfaces = get_available_interfaces()
        
        for title, component_class in available_interfaces.items():
            button = ctk.CTkButton(self.nav_button_frame, text=title, 
                                   command=lambda cls=component_class: self.switch_interface(cls))
            button.pack(fill="x", pady=5)
            
            instance = component_class(self.main_content_frame, self)
            self.interface_instances[title] = instance


    def switch_interface(self, component_class: Type[BaseInterface]):
        """切换显示的内容界面。"""
        new_title = component_class.get_title()
        component_instance = self.interface_instances[new_title]
        
        if self.current_component:
            self.current_component.pack_forget()
            self.current_component.on_switch_away() 

        self.current_component = component_instance
        
        if not component_instance.winfo_children():
            component_instance.create_ui()

        component_instance.pack(fill="both", expand=True, padx=0, pady=0)
        component_instance.on_switch_to() 

    def _show_initial_interface(self):
        """默认显示第一个注册的界面（已按 order 排序）。"""
        if self.interface_instances:
            # 字典已由 interface_loader 按 order 排序，直接取第一个即可
            first_title = next(iter(self.interface_instances))
            first_class = get_available_interfaces()[first_title]
            self.switch_interface(first_class)
        else:
            ctk.CTkLabel(self.main_content_frame, text="未加载任何功能模块").pack(padx=50, pady=50)


if __name__ == "__main__":
    try:
        import systems_editor_plugin 
        import config_settings_plugin
        import systemslist_editor_plugin
        import gamelist_editor_plugin
        import media_preview_plugin
        import name_editor_plugin
    except ImportError:
        print("警告：请确保所有插件文件 (*_plugin.py) 已创建并位于同一目录下。")
        sys.exit(1)

    app = WindowShell()
    app.mainloop()