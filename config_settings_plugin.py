import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, Union, Dict, Any, Type
import platform
import xml.etree.ElementTree as ET 
import json
import sys 
import os

from base_interface import BaseInterface 
from interface_loader import register_interface

# --- 局部常量 ---
CONFIG_DIR_NAME = "config"
CONFIG_FILE_NAME = "esde_toolkit_config.json"
ES_DE_SYSTEMS_SUBPATH = Path("resources") / "systems"
SYSTEMS_FILES = ["es_systems.xml", "es_systems.cfg"] 
ES_SETTINGS_FILE = "es_settings.xml"
TOOL_VERSION = "0.0.1" # 插件版本号

CURRENT_OS_NAME: Optional[str] = None
current_os_raw = platform.system().lower()
if 'windows' in current_os_raw: CURRENT_OS_NAME = "windows"
elif 'darwin' in current_os_raw: CURRENT_OS_NAME = "macos"
elif 'linux' in current_os_raw: CURRENT_OS_NAME = "linux"


# --- 局部配置工具函数 (绝对独立) ---
def _get_config_file_path(filename: str) -> Path:
    """获取指定配置文件的完整路径。"""
    try:
        script_dir = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))).resolve()
    except NameError:
        script_dir = Path(os.getcwd())
    
    config_dir = script_dir / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True) 
    return config_dir / filename

def load_app_config() -> Dict[str, Optional[Any]]:
    """加载应用的持久化配置。"""
    config_path = _get_config_file_path(CONFIG_FILE_NAME)
    paths: Dict[str, Optional[Any]] = {
        "esde_root_path": None, "settings_config": None, "systems_dir": None,
        "rom_files_dir": None, "gamelist_base_dir": None, 
        "systems_config_file_found_path": None, 
        "target_os": None, "version": None,
    }
    
    if not config_path.is_file(): return paths
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in paths.keys():
                path_str = data.get(key)
                if path_str and path_str.lower() != 'none': 
                    if key not in ["target_os", "version"]:
                         paths[key] = Path(path_str)
                    else:
                         paths[key] = path_str
        return paths
    except Exception:
        return {k: None for k in paths} 

def save_app_config(config_info: Dict[str, Union[str, Optional[Path]]]):
    """保存应用的持久化配置。"""
    config_path = _get_config_file_path(CONFIG_FILE_NAME)
        
    data_to_save = {}
    for key, value in config_info.items():
        if key in ["target_os", "version"]:
             continue
             
        if isinstance(value, Path):
            data_to_save[key] = str(value)
        elif value is None:
            data_to_save[key] = ""
        else:
            data_to_save[key] = value

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
         messagebox.showerror("保存错误", f"无法保存配置到文件: {e}")
         pass


# --- 内部配置管理器 (绝对独立) ---
class _EsDeConfigManager:
    """管理 ES-DE 各种关键路径的查找、验证和状态。"""
    def __init__(self):
        initial_config = load_app_config()

        self.esde_root_path: Optional[Path] = initial_config.get("esde_root_path")
        self.settings_config_path: Optional[Path] = initial_config.get("settings_config")
        self.systems_dir_path: Optional[Path] = initial_config.get("systems_dir")
        self.rom_files_dir: Optional[Path] = initial_config.get("rom_files_dir")
        self.gamelist_base_dir: Optional[Path] = initial_config.get("gamelist_base_dir")
        self._systems_config_file_found_path: Optional[Path] = initial_config.get("systems_config_file_found_path")
        
        self.target_os: str = initial_config.get("target_os") or CURRENT_OS_NAME or "windows"
        
    def _validate_root_path(self, root_path: Path) -> bool:
        self.systems_dir_path = root_path / ES_DE_SYSTEMS_SUBPATH
        return self.systems_dir_path.is_dir()

    def _find_systems_config(self, systems_dir: Path) -> Optional[Path]:
        
        if CURRENT_OS_NAME:
            os_specific_dir = systems_dir / CURRENT_OS_NAME
            if os_specific_dir.is_dir():
                for filename in SYSTEMS_FILES:
                    file_path = os_specific_dir / filename
                    if file_path.is_file():
                        return file_path
        
        for filename in SYSTEMS_FILES:
            file_path = systems_dir / filename
            if file_path.is_file():
                return file_path
                
        return None

    def _read_rom_directory_from_settings(self, settings_path: Path) -> Optional[Path]:
        if not settings_path or not settings_path.is_file():
            return None
        try:
            raw_content = settings_path.read_text(encoding='utf-8', errors='ignore')
            
            if raw_content.strip().startswith('<?xml'):
                end_of_declaration = raw_content.find('?>')
                if end_of_declaration != -1:
                    raw_content = raw_content[end_of_declaration + 2:]
            
            cleaned_content = raw_content.strip()
            if not cleaned_content.startswith('<Settings>') and not cleaned_content.startswith('<settings>'):
                wrapped_content = f"<Settings>{cleaned_content}</Settings>"
            else:
                wrapped_content = cleaned_content
            
            root = ET.fromstring(wrapped_content)
            
            for element in root.findall('string'):
                if element.get('name') == 'ROMDirectory':
                    rom_dir_str = element.get('value')
                    if rom_dir_str:
                        return Path(rom_dir_str)
            
            return None
        except Exception:
            return None

    def _resolve_paths(self):
        if not self.esde_root_path or not self.systems_dir_path:
            return

        self._systems_config_file_found_path = self._find_systems_config(self.systems_dir_path)
        
        self.settings_config_path = None
        root_settings_path = self.esde_root_path / ES_SETTINGS_FILE
        if root_settings_path.is_file():
            self.settings_config_path = root_settings_path
        if not self.settings_config_path:
            search_pattern = Path("settings") / ES_SETTINGS_FILE
            found_paths = [p for p in self.esde_root_path.rglob(str(search_pattern)) if p.is_file()]
            if found_paths:
                found_paths.sort(key=lambda p: len(p.parts)) 
                self.settings_config_path = found_paths[0]

        self.rom_files_dir = None
        if self.settings_config_path:
             self.rom_files_dir = self._read_rom_directory_from_settings(self.settings_config_path)

        self.gamelist_base_dir = None
        search_dir_name = "gamelists"
        found_gamelist_dirs = [p for p in self.esde_root_path.rglob(search_dir_name) if p.is_dir()]
        if found_gamelist_dirs:
            found_gamelist_dirs.sort(key=lambda p: len(p.parts)) 
            self.gamelist_base_dir = found_gamelist_dirs[0]
        
    def clear_paths(self):
        self.esde_root_path = None
        self._systems_config_file_found_path = None
        self.settings_config_path = None
        self.systems_dir_path = None
        self.rom_files_dir = None
        self.gamelist_base_dir = None

    def select_root_directory(self, initialdir: Optional[Union[str, Path]] = None) -> bool:
        directory = filedialog.askdirectory(title="选择 ES-DE 主目录 (包含 resources/systems 文件夹)", initialdir=initialdir)
        if not directory: return False
        root_path = Path(directory)
        if not self._validate_root_path(root_path):
            messagebox.showwarning("验证失败", f"所选目录 '{root_path.name}' 似乎不是有效的 ES-DE 主目录。\n请确保它包含 'resources/systems' 文件夹。")
            self.clear_paths()
            return False 
        self.esde_root_path = root_path
        self._resolve_paths()
        return True

    def select_systems_directory(self, initialdir: Optional[Union[str, Path]] = None) -> bool:
        directory = filedialog.askdirectory(title="选择 Systems 配置目录 (包含 es_systems.xml)", initialdir=initialdir)
        if not directory: return False
        selected_dir_path = Path(directory)
        found_config_file = self._find_systems_config(selected_dir_path)
        if not found_config_file:
            messagebox.showwarning("警告", "所选目录下未找到有效的 es_systems.xml 或 es_systems.cfg 文件。")
            return False
        self.systems_dir_path = selected_dir_path
        self._systems_config_file_found_path = found_config_file
        return True

    def select_settings_file(self, initialdir: Optional[Union[str, Path]] = None) -> bool:
        file_path_str = filedialog.askopenfilename(title="选择 es_settings.xml", initialdir=initialdir, filetypes=[("ES-DE Settings File", "*.xml"), ("All Files", "*.*")])
        if not file_path_str: return False
        self.settings_config_path = Path(file_path_str)
        return True
    
    def select_rom_files_directory(self, initialdir: Optional[Union[str, Path]] = None) -> bool:
        directory = filedialog.askdirectory(title="选择 游戏文件目录 (ROMs 所在的根目录)", initialdir=initialdir)
        if not directory: return False
        self.rom_files_dir = Path(directory)
        return True
    
    def select_gamelist_base_dir(self, initialdir: Optional[Union[str, Path]] = None) -> bool:
        directory = filedialog.askdirectory(title="选择 游戏列表根目录 (包含 gamelist.xml 的目录)", initialdir=initialdir)
        if not directory: return False
        self.gamelist_base_dir = Path(directory)
        return True
        
    def get_config_info(self) -> Dict[str, Union[str, Optional[Path]]]:
        # 不包含 version
        return {
            "esde_root_path": self.esde_root_path,
            "settings_config": self.settings_config_path,
            "systems_dir": self.systems_dir_path,
            "rom_files_dir": self.rom_files_dir,
            "gamelist_base_dir": self.gamelist_base_dir,
            "systems_config_file_found_path": self._systems_config_file_found_path, 
            
            "target_os": self.target_os.lower(), # UI 中仍然需要知道目标 OS
        }
        
    def validate_paths(self) -> bool:
        """保存前的路径验证。"""
        paths = self.get_config_info()
        systems_config_file_found = self._systems_config_file_found_path

        if not paths['esde_root_path']:
            messagebox.showwarning("路径缺失", "请先选择 ES-DE 主目录。")
            return False
        
        if not systems_config_file_found:
             messagebox.showwarning("路径缺失", "未能找到有效的 es_systems 配置文件。请检查目录或手动选择。")
             return False

        if not paths['rom_files_dir']:
            messagebox.showwarning("路径缺失", "未能确定游戏文件目录 (ROMs)。请手动选择或确保 es_settings.xml 正确。")
            return False
            
        if not paths['gamelist_base_dir']:
            messagebox.showwarning("路径缺失", "未能找到游戏列表根目录 (Gamelists)。请手动选择。")
            return False
             
        return True


# --- 插件类 (ConfigSettingsPlugin) ---
class ConfigSettingsPlugin(BaseInterface):

    @staticmethod
    def get_title() -> str:
        return "基础路径设置"
    
    @staticmethod
    def get_order() -> int:
        return 10 # 确保配置界面显示在第一个位置
    
    def __init__(self, master: Any, app_ref: Any, **kwargs):
        super().__init__(master, app_ref, **kwargs)
        
        self.config_manager = _EsDeConfigManager() 
        
        self.root_path_var = ctk.StringVar()
        self.systems_path_var = ctk.StringVar()
        self.settings_path_var = ctk.StringVar()
        self.rom_files_dir_var = ctk.StringVar() 
        self.gamelist_base_var = ctk.StringVar() 

        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(6, weight=1) 

    def create_ui(self):
        self.config_manager = _EsDeConfigManager() # 确保在创建UI时重新加载最新配置

        row = 0
        ctk.CTkLabel(self, text="ES-DE 主目录:", width=150, anchor="w").grid(row=row, column=0, padx=10, pady=(10, 5), sticky="w")
        ctk.CTkEntry(self, textvariable=self.root_path_var, state="readonly").grid(row=row, column=1, padx=5, pady=(10, 5), sticky="ew")
        ctk.CTkButton(self, text="自动选择/解析", command=self._auto_select_root, width=120).grid(row=row, column=2, padx=10, pady=(10, 5), sticky="e")

        row += 1
        ctk.CTkLabel(self, text="Systems 配置 (es_systems.xml)目录:", width=150, anchor="w").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(self, textvariable=self.systems_path_var, state="readonly").grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self, text="手动选择目录", command=self._manual_select_systems_directory, width=120).grid(row=row, column=2, padx=10, pady=5, sticky="e")
        
        row += 1
        ctk.CTkLabel(self, text="Settings 配置 (es_settings.xml):", width=150, anchor="w").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(self, textvariable=self.settings_path_var, state="readonly").grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self, text="手动选择文件", command=self._manual_select_settings, width=120).grid(row=row, column=2, padx=10, pady=5, sticky="e")

        row += 1
        ctk.CTkLabel(self, text="游戏文件目录 (ROMs):", width=150, anchor="w").grid(row=row, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkEntry(self, textvariable=self.rom_files_dir_var, state="readonly").grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(self, text="手动选择目录", command=self._manual_select_rom_files_directory, width=120).grid(row=row, column=2, padx=10, pady=5, sticky="e")
        
        row += 1
        ctk.CTkLabel(self, text="游戏列表根目录 (Gamelists):", width=150, anchor="w").grid(row=row, column=0, padx=10, pady=(5, 10), sticky="w")
        ctk.CTkEntry(self, textvariable=self.gamelist_base_var, state="readonly").grid(row=row, column=1, padx=5, pady=(5, 10), sticky="ew")
        ctk.CTkButton(self, text="手动选择目录", command=self._manual_select_gamelist_base, width=120).grid(row=row, column=2, padx=10, pady=(5, 10), sticky="e")
        
        # 底部按钮区
        bottom_buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_buttons_frame.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky="se")

        ctk.CTkButton(bottom_buttons_frame, text="保存所有路径", command=self.save_config).pack(side="right", padx=5)

        self._update_ui()
        
    def _update_ui(self):
        info = self.config_manager.get_config_info()
        systems_config_file_found = self.config_manager._systems_config_file_found_path

        self.root_path_var.set(str(info['esde_root_path']) if info['esde_root_path'] else "未选择")
        self.systems_path_var.set(str(systems_config_file_found) if systems_config_file_found else "未加载 Systems 文件")
        self.settings_path_var.set(str(info['settings_config']) if info['settings_config'] else "未找到 (可选)")
        self.rom_files_dir_var.set(str(info['rom_files_dir']) if info['rom_files_dir'] else "未找到 (从 es_settings.xml 读取)")
        self.gamelist_base_var.set(str(info['gamelist_base_dir']) if info['gamelist_base_dir'] else "未找到 (通常是 [主目录]/gamelists)")


    def _auto_select_root(self):
        initial_dir = self.config_manager.esde_root_path or Path.home()
        self.config_manager.select_root_directory(initialdir=initial_dir)
        self._update_ui()

    def _manual_select_systems_directory(self):
        initial_dir = self.config_manager.systems_dir_path or self.config_manager.esde_root_path or Path.home()
        self.config_manager.select_systems_directory(initialdir=initial_dir)
        self._update_ui()

    def _manual_select_settings(self):
        initial_dir = self.config_manager.esde_root_path or Path.home()
        if self.config_manager.select_settings_file(initialdir=initial_dir):
            self.config_manager._resolve_paths() # 重新解析rom目录
            self._update_ui()
            
    def _manual_select_rom_files_directory(self):
        initial_dir = self.config_manager.rom_files_dir or self.config_manager.esde_root_path or Path.home()
        self.config_manager.select_rom_files_directory(initialdir=initial_dir)
        self._update_ui()
            
    def _manual_select_gamelist_base(self):
        initial_dir = self.config_manager.gamelist_base_dir or self.config_manager.esde_root_path or Path.home()
        self.config_manager.select_gamelist_base_dir(initialdir=initial_dir)
        self._update_ui()
            
    def save_config(self):
        """保存配置，作为 BaseInterface 的标准方法。"""
        if self.config_manager.validate_paths():
            # 1. 保存配置到文件
            save_app_config(self.config_manager.get_config_info())
            
            messagebox.showinfo("保存成功", "所有基础路径配置已成功保存！")

# 在文件末尾进行注册
register_interface(ConfigSettingsPlugin.get_title(), ConfigSettingsPlugin.get_order(), ConfigSettingsPlugin)