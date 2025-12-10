import customtkinter as ctk
from tkinter import messagebox, filedialog 
import xml.etree.ElementTree as ET
from pathlib import Path 
import re 
import platform
from typing import Optional, Any, Dict, List, Tuple, Union, Set
import sys
import json 
import os 
import shutil 
import datetime 

try:
    from base_interface import BaseInterface 
    from interface_loader import register_interface
except ImportError:
    class BaseInterface(ctk.CTkFrame):
        def __init__(self, master, app_ref, **kwargs):
            super().__init__(master, **kwargs)
            self.app_ref = app_ref
    def register_interface(title, order, cls):
        pass


__version__ = "0.1.2" 

LIST_FRAME_BG_COLOR = "#202020"  
LIST_ITEM_NORMAL_BG = LIST_FRAME_BG_COLOR 
LIST_ITEM_SELECTED_BG = "#6C3483" 
LIST_TEXT_COLOR = "#FFFFFF" 
CONFIG_FILE_NAME = "esde_toolkit_config.json" 
EMU_CONFIG_FILE_NAME = "emulator_cores_config.json" 
CONFIG_DIR_NAME = "config"
SYSTEMS_FILES = ["es_systems.xml"] 
FIND_RULES_FILE_NAME = "es_find_rules.xml" 
SYSTEMS_FILE_CONFIG_KEY = "systems_config_file_found_path"
BACKUP_DIR_NAME = "backups" 
ES_DE_SYSTEMS_SUBPATH = Path("resources") / "systems"
LOCAL_SYSTEMS_FILE_NAME = "es_systems_local.xml"

OS_OPTIONS = ["windows", "linux", "macos", "unix", "haiku", "android"]
TARGET_OS_KEY = "target_os"

EMULATOR_VARIABLES: Dict[str, Dict[str, Any]] = {}
RETROARCH_CORES_MOCK: List[str] = []

SYSTEMS_INSTRUCTION_CONTENT = """
**重要警告：**
修改系统配置文件（es_systems.xml）中的字符串信息（尤其是命令代码和路径）可能会导致 EmulationStation-DE 无法启动或游戏无法运行。
**在进行任何修改前，强烈建议使用“备份/还原”功能创建当前配置的备份！**

1. 系统详细信息 (System Details)：
   - 显示名称 (Fullname)：显示在 ES-DE 界面上的名称。
   - 路径 (Path)：通常使用 %ROMPATH% 变量作为 ROMs 文件夹的占位符。
   - 扩展名 (Extension)：支持的文件扩展名列表，使用空格分隔 (例如：.zip .7z .iso)。
   - 平台/主题 (Platform/Theme)：格式为 'platform / theme'。如果主题与平台名称相同，则只需填写平台名。

2. 模拟器/命令 (Emulator/Command)：
   - 配置名 (Label)：模拟器配置的唯一名称。
   - 配置代码 (Cmd)：实际运行游戏的命令代码。

常用命令变量：
   - %ROM%：游戏文件的完整路径。
   - %EMULATOR_RETROARCH%：RetroArch 模拟器路径。
   - %CORE_RETROARCH%：RetroArch 核心目录路径。
   - %EMULATOR_DEFAULT%：系统配置中默认模拟器的变量。
   - **%EMULATOR_XXX%**：来自 es_find_rules.xml 中定义的独立模拟器变量。
   
提示：点击 '自定义命令' 按钮可以使用预设的模拟器和核心快速生成命令代码。
**致谢：GitHub上的各个开源库**
本项目由（爱折腾的老家伙）与 **Gemini AI**（人工智障）携手合作，共同折腾完成，旨在为玩家提供便捷的配置管理体验。
"""

def _get_base_emulator_variables() -> Dict[str, Dict[str, Any]]:
    return {
        "RetroArch (系统默认)": {"variable": "%EMULATOR_RETROARCH%", "needs_core": True, "core_var": "%CORE_RETROARCH%", "command_templates": []},
        "默认模拟器 (从系统配置继承)": {"variable": "%EMULATOR_DEFAULT%", "needs_core": False, "core_var": "", "command_templates": []},
        "--- 自定义路径/EXE (无需变量) ---": {"variable": "__CUSTOM_PATH__", "needs_core": False, "core_var": "", "command_templates": []},
    }

def _get_config_file_path(filename: str) -> Path:
    try:
        script_dir = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))).resolve()
    except NameError:
        script_dir = Path(os.getcwd())
    
    config_dir = script_dir / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True) 
    return config_dir / filename

def get_backup_dir_path() -> Path:
    config_path = _get_config_file_path(CONFIG_FILE_NAME) 
    backup_dir = config_path.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir

def load_app_config_systems() -> Dict[str, Optional[Any]]:
    config_path = _get_config_file_path(CONFIG_FILE_NAME)
    paths: Dict[str, Optional[Any]] = {
        "esde_root_path": None, 
        SYSTEMS_FILE_CONFIG_KEY: None, 
        TARGET_OS_KEY: "windows",
    }
    
    if not config_path.is_file(): return paths
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            esde_root_path_str = data.get("esde_root_path")
            if esde_root_path_str and esde_root_path_str.lower() != 'none': 
                paths["esde_root_path"] = Path(esde_root_path_str)

            full_path_str = data.get(SYSTEMS_FILE_CONFIG_KEY)
            if full_path_str and full_path_str.lower() != 'none':
                full_path = Path(full_path_str)
                if len(full_path.parts) >= 2 and full_path.name.lower() == SYSTEMS_FILES[0]:
                    paths[SYSTEMS_FILE_CONFIG_KEY] = full_path.parent.parent
                else:
                    paths[SYSTEMS_FILE_CONFIG_KEY] = None 
                    
        return paths
    except Exception:
        return {k: None if k != TARGET_OS_KEY else "windows" for k in paths}

def save_app_config_systems(paths: Dict[str, Optional[Any]]):
    pass 


def load_systems_file(path: Union[str, Path]) -> Optional[ET.ElementTree]:
    try:
        content = Path(path).read_text(encoding='utf-8')
        content = re.sub(' xmlns="[^"]+"', '', content, count=1)
        tree = ET.ElementTree(ET.fromstring(content))
        return tree
    except Exception as e:
        messagebox.showerror("文件加载错误", f"无法解析系统配置文件: {e}")
        return None

def save_systems_file(path: Union[str, Path], tree: ET.ElementTree):
    path_obj = Path(path)
    
    try:
        tree.write(path_obj, encoding='utf-8', xml_declaration=True)
        messagebox.showinfo("提示", f"系统配置已保存到:\n{path_obj.name}")
    except Exception as e:
        messagebox.showerror("保存失败", f"保存系统配置文件时发生错误: {e}")

def get_core_ext(target_os: str) -> str:
    target_os = target_os.lower()
    if target_os == "windows":
        return ".dll"
    elif target_os == "macos":
        return ".dylib"
    elif target_os in ["linux", "unix", "haiku", "android"]: 
        return ".so"
    return ""
    
def _extract_retroarch_cores_from_xml(systems_file_path: Path) -> List[str]:
    cores = set()
    try:
        content = systems_file_path.read_text(encoding='utf-8')
        content = re.sub(' xmlns="[^"]+"', '', content, count=1)
        root = ET.fromstring(content)
        
        core_regex = re.compile(r'%CORE_RETROARCH%[/\\]["\']?([^"\']+\.(?:dll|so|dylib))["\']?', re.IGNORECASE)
        
        for system_element in root.findall('system'):
            for command_element in system_element.findall('command'):
                command_text = command_element.text
                if command_text:
                    match = core_regex.search(command_text)
                    if match:
                        cores.add(match.group(1))
        
    except Exception:
        pass
    return list(cores)


def _extract_emulators_from_find_rules(find_rules_file_path: Path) -> Dict[str, Dict[str, Any]]:
    emulators: Dict[str, Dict[str, Any]] = {}
    if not find_rules_file_path.is_file():
        return emulators
        
    try:
        content = find_rules_file_path.read_text(encoding='utf-8')
        content = re.sub(' xmlns="[^"]+"', '', content, count=1) 
        root = ET.fromstring(content)
        
        core_names: Set[str] = set()
        for core_element in root.findall('core'):
            core_name = core_element.get('name')
            if core_name:
                core_names.add(core_name.upper())
        
        for emulator_element in root.findall('emulator'):
            emu_name = emulator_element.get('name')
            if emu_name:
                emu_name_upper = emu_name.upper()
                variable = f"%EMULATOR_{emu_name_upper}%"
                
                needs_core = emu_name_upper in core_names
                core_var = f"%CORE_{emu_name_upper}%" if needs_core else ""
                
                friendly_name = re.sub(r'[^a-zA-Z0-9]', ' ', emu_name).title().strip()
                if not friendly_name:
                    friendly_name = emu_name
                
                display_key = f"{friendly_name} (独立模拟器 {variable})"

                if display_key not in emulators:
                     emulators[display_key] = {
                        "variable": variable, 
                        "needs_core": needs_core, 
                        "core_var": core_var,
                        "command_templates": [],
                    }
                        
        return emulators
    except Exception:
        return {}


def _extract_commands_from_systems_xml(systems_file_path: Path, emu_var_to_key: Dict[str, str]) -> Dict[str, List[Dict[str, str]]]:
    
    command_templates: Dict[str, List[Dict[str, str]]] = {}
    if not systems_file_path.is_file():
        return command_templates
    
    try:
        content = systems_file_path.read_text(encoding='utf-8')
        content = re.sub(' xmlns="[^"]+"', '', content, count=1)
        root = ET.fromstring(content)
        
        sorted_vars = sorted(emu_var_to_key.keys(), key=len, reverse=True)
        
        for system_element in root.findall('system'):
            for command_element in system_element.findall('command'):
                command_text = command_element.text
                command_label = command_element.get('label')
                
                if command_text and command_label:
                    
                    found_emu_var = None
                    for emu_var in sorted_vars:
                        if emu_var in command_text:
                            found_emu_var = emu_var
                            break
                    
                    if found_emu_var:
                        display_key = emu_var_to_key[found_emu_var]
                        
                        template = {"label": command_label, "cmd": command_text.strip()}
                        
                        if display_key not in command_templates:
                            command_templates[display_key] = []
                        
                        if template not in command_templates[display_key]:
                            command_templates[display_key].append(template)
                            
    except Exception:
        pass
        
    return command_templates


def load_or_create_emu_config(target_os: str = "windows", systems_file_path: Optional[Path] = None):
    global EMULATOR_VARIABLES, RETROARCH_CORES_MOCK
    
    config_path = _get_config_file_path(EMU_CONFIG_FILE_NAME)
    
    base_emu_vars = _get_base_emulator_variables()
    
    extracted_emu_vars: Dict[str, Dict[str, Any]] = {}
    find_rules_file_path: Optional[Path] = None
    if systems_file_path and systems_file_path.is_file():
        find_rules_file_path = systems_file_path.parent / FIND_RULES_FILE_NAME
        extracted_emu_vars = _extract_emulators_from_find_rules(find_rules_file_path)

    all_emu_vars = base_emu_vars.copy()
    all_emu_vars.update(extracted_emu_vars)
    
    emu_var_to_key = {details["variable"]: key for key, details in all_emu_vars.items()}
    
    command_templates: Dict[str, List[Dict[str, str]]] = {}
    if systems_file_path and systems_file_path.is_file():
        command_templates = _extract_commands_from_systems_xml(systems_file_path, emu_var_to_key)
    
    config: Dict[str, Any] = {}
    custom_cores: List[str] = []
    xml_cores_saved: List[str] = []
    saved_emu_vars: Dict[str, Dict[str, Any]] = {} 

    if config_path.is_file():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            custom_cores = config.get("custom_retroarch_cores", [])
            xml_cores_saved = config.get("xml_extracted_retroarch_cores", [])
            saved_emu_vars = config.get("emulator_variables", {})
        except Exception:
            pass
    
    xml_cores_latest: List[str] = []
    if systems_file_path and systems_file_path.is_file():
        xml_cores_latest = _extract_retroarch_cores_from_xml(systems_file_path)
    else:
        xml_cores_latest = xml_cores_saved
    
    final_emu_vars = all_emu_vars.copy()
    
    if not extracted_emu_vars and saved_emu_vars and len(saved_emu_vars) > len(base_emu_vars):
        final_emu_vars = saved_emu_vars.copy()
        final_emu_vars.update(base_emu_vars)
    
    for key, templates in command_templates.items():
        if key in final_emu_vars:
            final_emu_vars[key]["command_templates"] = templates
            
    EMULATOR_VARIABLES = final_emu_vars 
    
    unique_cores = set(xml_cores_latest)
    unique_cores.update(custom_cores) 
    
    RETROARCH_CORES_MOCK = sorted(list(unique_cores))
    
    data_to_save = {
        "emulator_variables": final_emu_vars, 
        "custom_retroarch_cores": custom_cores, 
        "xml_extracted_retroarch_cores": xml_cores_latest, 
    }
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


class CTkListFrame(ctk.CTkFrame):
    def __init__(self, master, editor_ref, list_id, **kwargs):
        super().__init__(master, **kwargs)
        self.editor_ref = editor_ref
        self.list_id = list_id
        self.data: Dict[str, Any] = {} 
        self.selected_key: Optional[str] = None
        self.buttons: Dict[str, ctk.CTkFrame] = {} 
        
        self.listbox_frame = ctk.CTkScrollableFrame(self)
        self.listbox_frame.pack(fill="both", expand=True, padx=5, pady=5)

    def _select_item(self, key, item_frame):
        
        old_key = self.selected_key
        if self.selected_key == key: 
            self.selected_key = None
            item_frame.configure(fg_color=LIST_ITEM_NORMAL_BG)
            self.editor_ref.listbox_selected(None, self.list_id) 
            return
            
        if old_key and old_key in self.buttons:
            self.buttons[old_key].configure(fg_color=LIST_ITEM_NORMAL_BG)

        self.selected_key = key
        item_frame.configure(fg_color=LIST_ITEM_SELECTED_BG)
        
        self.editor_ref.listbox_selected(key, self.list_id)

    def update_list(self, new_data: Dict[str, Any], reselect_key: Optional[str] = None):
        for widget in self.listbox_frame.winfo_children():
            widget.destroy()
        
        self.data = new_data
        self.buttons = {}
        
        keys = sorted(new_data.keys(), key=lambda k: new_data[k])
        
        current_select_key = reselect_key if reselect_key in keys else (self.selected_key if self.selected_key in keys else None)
        self.selected_key = None 

        for key in keys:
            display_text = new_data[key] 
            
            frame = ctk.CTkFrame(self.listbox_frame, fg_color=LIST_ITEM_NORMAL_BG)
            frame.pack(fill="x", padx=2, pady=1)
            
            label = ctk.CTkLabel(frame, text=display_text, anchor="w", cursor="hand2", text_color=LIST_TEXT_COLOR, wraplength=450)
            label.pack(fill="x", padx=5, pady=2)
            
            self.buttons[key] = frame 
            
            frame.bind("<Button-1>", lambda event, k=key, f=frame: self._select_item(k, f))
            label.bind("<Button-1>", lambda event, k=key, f=frame: self._select_item(k, f))
            
            if current_select_key == key:
                self.selected_key = key
                frame.configure(fg_color=LIST_ITEM_SELECTED_BG)


class BackupRestoreWindow(ctk.CTkToplevel):
    def __init__(self, master, app_ref, systems_editor):
        super().__init__(master)
        self.app_ref = app_ref
        self.systems_editor = systems_editor
        self.title("备份与还原工具")
        self.geometry("600x400")
        self.transient(master)
        self.grab_set()

        self.backup_dir = get_backup_dir_path()
        self.backup_list: Dict[str, Path] = {}

        self._setup_ui()
        self._refresh_backup_list()

    def _setup_ui(self):
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill="x", padx=20, pady=(10, 5))

        ctk.CTkLabel(control_frame, text="当前文件:", text_color="yellow").pack(side="left", padx=10)
        file_path_text = self.systems_editor.systems_file_path.name if self.systems_editor.systems_file_path else "未加载 Systems 文件"
        ctk.CTkLabel(control_frame, text=file_path_text, text_color="yellow").pack(side="left")

        ctk.CTkButton(control_frame, text="新建备份", command=self.create_backup, fg_color="#2ECC71").pack(side="right", padx=10)
        
        list_label = ctk.CTkLabel(self, text="已有备份列表 (名称 | 大小 | 创建时间)", font=ctk.CTkFont(weight="bold"))
        list_label.pack(fill="x", padx=20, pady=(10, 0))
        
        self.list_frame = CTkListFrame(self, self, 'backup', fg_color=LIST_FRAME_BG_COLOR)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=5)

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", padx=20, pady=10)
        btn_frame.columnconfigure((0, 1, 2), weight=1)

        self.restore_btn = ctk.CTkButton(btn_frame, text="还原选中备份", command=self.restore_backup, fg_color="#3498DB", state="disabled")
        self.restore_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.delete_btn = ctk.CTkButton(btn_frame, text="删除选中备份", command=self.delete_backup, fg_color="#E74C3C", state="disabled")
        self.delete_btn.grid(row=0, column=1, padx=5, sticky="ew")
        
        ctk.CTkButton(btn_frame, text="关闭", command=self.destroy).grid(row=0, column=2, padx=(5, 0), sticky="ew")
        
    def listbox_selected(self, key: Optional[str], list_id: str):
        is_selected = key is not None
        self.restore_btn.configure(state="normal" if is_selected and self.systems_editor.systems_file_path else "disabled")
        self.delete_btn.configure(state="normal" if is_selected else "disabled")

    def _refresh_backup_list(self, reselect_key: Optional[str] = None):
        self.backup_list = {}
        files = sorted(self.backup_dir.glob("*.xml"), reverse=True)
        
        display_data = {}
        for f in files:
            try:
                stat = f.stat()
                size_kb = f"{stat.st_size / 1024:.1f} KB"
                mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                display_name = f"{f.name} | {size_kb} | {mod_time}"
                
                self.backup_list[display_name] = f
                display_data[display_name] = display_name
            except Exception:
                pass

        self.list_frame.update_list(display_data, reselect_key=reselect_key)
        
    def create_backup(self):
        if not self.systems_editor.systems_file_path or not self.systems_editor.systems_file_path.is_file():
            messagebox.showwarning("警告", "请先加载一个有效的 Systems 文件才能创建备份。")
            return

        current_file = self.systems_editor.systems_file_path
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{current_file.stem}_{timestamp}{current_file.suffix}"
        backup_path = self.backup_dir / backup_name
        
        try:
            shutil.copy2(current_file, backup_path)
            
            size_kb = f"{backup_path.stat().st_size / 1024:.1f} KB"
            mod_time = datetime.datetime.fromtimestamp(backup_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            reselect_key = f"{backup_name} | {size_kb} | {mod_time}"

            self._refresh_backup_list(reselect_key=reselect_key) 
            messagebox.showinfo("成功", f"备份已创建: {backup_name}")
        except Exception as e:
            messagebox.showerror("备份失败", f"创建备份时发生错误: {e}")

    def restore_backup(self):
        selected_key = self.list_frame.selected_key
        if not selected_key or not self.systems_editor.systems_file_path:
            messagebox.showwarning("警告", "请先选中一个备份文件，并确保已加载 Systems 文件路径。")
            return

        backup_filename = selected_key.split(' | ')[0]
        backup_file = self.backup_dir / backup_filename
        
        if not backup_file.is_file():
            messagebox.showerror("错误", "找不到备份文件。")
            return
            
        target_file = self.systems_editor.systems_file_path
        
        if not messagebox.askyesno("确认还原", f"确定使用 '{backup_file.name}' 覆盖当前配置文件 '{target_file.name}' 吗?\n(建议先创建当前配置的备份)"):
            return
            
        try:
            shutil.copy2(backup_file, target_file)
            self.systems_editor.load_config(target_file) 
            
            target_os = self.systems_editor._last_processed_os
            load_or_create_emu_config(target_os=target_os, systems_file_path=target_file)
            
            if hasattr(self.app_ref, '_update_status_display'):
                 self.app_ref._update_status_display() 
                 
            messagebox.showinfo("成功", "配置已还原并已自动重新加载。")
            self.destroy()
        except Exception as e:
            messagebox.showerror("还原失败", f"还原文件时发生错误: {e}")

    def delete_backup(self):
        selected_key = self.list_frame.selected_key
        if not selected_key:
            messagebox.showwarning("警告", "请先选中一个备份文件才能删除。")
            return

        backup_filename = selected_key.split(' | ')[0]
        backup_file = self.backup_dir / backup_filename
        
        if not messagebox.askyesno("确认删除", f"确定永久删除备份文件 '{backup_file.name}' 吗?"):
            return
            
        try:
            backup_file.unlink()
            self._refresh_backup_list()
            messagebox.showinfo("成功", f"备份文件已删除。")
        except Exception as e:
            messagebox.showerror("删除失败", f"删除文件时发生错误: {e}")


class BasicCommandSelector(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("基础命令选择")
        self.geometry("600x650")
        self.result_command: Optional[str] = None
        self.selected_core_path: Optional[str] = None
        self.transient(master) 
        self.grab_set() 
        
        self.current_selection = ctk.StringVar()
        self._setup_ui()
        
        master.wait_window(self) 
        
    def _setup_ui(self):
        emu_frame = ctk.CTkFrame(self)
        emu_frame.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(emu_frame, text="选择模拟器:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        
        emu_options = list(EMULATOR_VARIABLES.keys())
        self.current_selection.set(emu_options[0] if emu_options else "")
        self.emu_option_menu = ctk.CTkOptionMenu(
            emu_frame, 
            values=emu_options,
            variable=self.current_selection, 
            command=self._on_emu_change
        )
        self.emu_option_menu.pack(fill="x")
        
        self.cmd_template_frame = ctk.CTkFrame(self)
        self.cmd_template_frame.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.cmd_template_frame, text="选择预设命令 (可选，点击选中后将直接使用):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.cmd_template_list = CTkListFrame(self.cmd_template_frame, self, 'cmd_template', fg_color=LIST_FRAME_BG_COLOR, height=150)
        self.cmd_template_list.pack(fill="both", expand=True)

        self.core_frame = ctk.CTkFrame(self)
        ctk.CTkLabel(self.core_frame, text="选择 RetroArch 核心 (仅当选择 RetroArch 时):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        
        core_btns = ctk.CTkFrame(self.core_frame, fg_color="transparent")
        core_btns.pack(fill="x", pady=(0, 5))
        self.add_core_btn = ctk.CTkButton(core_btns, text="添加自定义核心路径", command=self.add_custom_core)
        self.add_core_btn.pack(side="left")
        
        self.core_list_frame = CTkListFrame(self.core_frame, self, 'core', fg_color=LIST_FRAME_BG_COLOR, height=150)
        self.core_list_frame.pack(fill="both", expand=True)

        ctk.CTkButton(self, text="生成并使用命令", command=self.confirm, fg_color="#2ECC71").pack(padx=20, pady=10)
        
        self._on_emu_change(self.current_selection.get())


    def listbox_selected(self, key: Optional[str], list_id: str):
        if list_id == 'core':
            self.selected_core_path = key
        elif list_id == 'cmd_template':
            if key is not None:
                self._use_selected_template(key)
            else:
                self.core_list_frame.selected_key = None
                self.core_list_frame.update_list(self.core_list_frame.data)
                self.selected_core_path = None
            
    def _on_emu_change(self, selection):
        details = EMULATOR_VARIABLES.get(selection)
        
        if not details:
            self.core_frame.pack_forget()
            self.cmd_template_frame.pack_forget()
            return
            
        is_needs_core = details.get('needs_core', False)
        
        self.cmd_template_list.selected_key = None
        self.cmd_template_list.update_list({})
        
        templates = details.get("command_templates", [])
        if templates:
            self.cmd_template_frame.pack(padx=20, pady=5, fill="x")
            cmd_data = {}
            for t in templates:
                display = f"[{t['label']}] {t['cmd']}"
                cmd_data[t['label']] = display
            
            self.cmd_template_list.update_list(cmd_data)
        else:
            self.cmd_template_frame.pack_forget()


        self.selected_core_path = None
        if is_needs_core and details["variable"] != "__CUSTOM_PATH__":
            self.core_frame.pack(padx=20, pady=5, fill="both", expand=True)
            self.core_list_frame.update_list({core: core for core in RETROARCH_CORES_MOCK})
        else:
            self.core_frame.pack_forget()

        
    def _use_selected_template(self, selected_template_label):
        selected_emu = self.current_selection.get()
        details = EMULATOR_VARIABLES.get(selected_emu)
        
        if not details:
            return

        selected_template = next(
            (t for t in details.get("command_templates", []) if t["label"] == selected_template_label), 
            None
        )
        
        if selected_template:
            self.result_command = selected_template["cmd"].strip()
            self.destroy()

            
    def add_custom_core(self):
        if hasattr(self.master, '_last_processed_os'):
            target_os = self.master._last_processed_os
        else:
            target_os = "windows"
            
        core_ext = get_core_ext(target_os)
        
        filetypes = [
            ("Core", f"*{core_ext}"), 
            ("All Cores", "*.dll *.so *.dylib"), 
            ("All", "*.*")
        ]
        f = filedialog.askopenfilename(title="选择核心文件", filetypes=filetypes)
        
        if f:
            name = Path(f).name
            
            if core_ext and not name.lower().endswith(core_ext.lower()):
                 if not messagebox.askyesno("警告", f"所选核心文件 '{name}' 的扩展名不是当前目标操作系统 ({target_os.capitalize()}) 所期望的 '{core_ext}'。\n确定仍然添加吗？"):
                     return

            if name not in RETROARCH_CORES_MOCK:
                RETROARCH_CORES_MOCK.append(name)
                
                try:
                    config_path = _get_config_file_path(EMU_CONFIG_FILE_NAME)
                    
                    config = {}
                    if config_path.is_file():
                        with open(config_path, 'r', encoding='utf-8') as file:
                            config = json.load(file)
                    
                    custom_cores = config.get("custom_retroarch_cores", [])
                    if name not in custom_cores:
                        custom_cores.append(name) 
                    
                    data_to_save = {
                        "custom_retroarch_cores": custom_cores,
                        "xml_extracted_retroarch_cores": config.get("xml_extracted_retroarch_cores", []),
                        "emulator_variables": config.get("emulator_variables", _get_base_emulator_variables()),
                    }
                    
                    with open(config_path, 'w', encoding='utf-8') as file:
                        json.dump(data_to_save, file, ensure_ascii=False, indent=4)
                except Exception:
                    pass 

            self.core_list_frame.update_list({core: core for core in RETROARCH_CORES_MOCK}, reselect_key=name)
            self.selected_core_path = name
            
    def confirm(self):
        selected_emu = self.current_selection.get()
        details = EMULATOR_VARIABLES.get(selected_emu)
        
        if not details:
            messagebox.showwarning("错误", "请选择一个模拟器。")
            return
            
        path = details["variable"]
        is_retro = details["needs_core"]

        if self.cmd_template_list.selected_key:
            self._use_selected_template(self.cmd_template_list.selected_key)
            return

        if path == "__CUSTOM_PATH__":
            f = filedialog.askopenfilename(
                title="选择自定义模拟器路径", 
                filetypes=[("可执行文件/脚本", "*.exe *.sh *.bat *.app"), ("所有文件", "*.*")]
            )
            if not f:
                messagebox.showwarning("取消", "未选择文件，操作已取消。")
                return
            
            path_obj = Path(f)
            custom_emu_path = f'"{path_obj.as_posix()}"'
            is_retroarch_custom = path_obj.name.lower() in ["retroarch.exe", "retroarch"]
            new_cmd = ""
            
            if is_retroarch_custom:
                core_f = filedialog.askopenfilename(
                    title="选择 RetroArch 核心文件 (.dll/.so/.dylib)", 
                    filetypes=[("RetroArch Core", "*.dll *.so *.dylib"), ("所有文件", "*.*")]
                )
                if not core_f:
                    messagebox.showwarning("取消", "已选择 RetroArch，但未选择核心文件，操作已取消。")
                    return
                
                core_path_obj = Path(core_f)
                core_var = "%CORE_RETROARCH%"
                core_p = f'"{core_var}/{core_path_obj.name}"'
                new_cmd = f'{custom_emu_path} -L {core_p} "%ROM%"'
                
                if core_path_obj.name not in RETROARCH_CORES_MOCK:
                    RETROARCH_CORES_MOCK.append(core_path_obj.name)
                    try:
                        config_path = _get_config_file_path(EMU_CONFIG_FILE_NAME)
                        
                        config = {}
                        if config_path.is_file():
                            with open(config_path, 'r', encoding='utf-8') as file:
                                config = json.load(file)
                        
                        custom_cores = config.get("custom_retroarch_cores", [])
                        if core_path_obj.name not in custom_cores:
                            custom_cores.append(core_path_obj.name) 
                        
                        data_to_save = {
                            "custom_retroarch_cores": custom_cores,
                            "xml_extracted_retroarch_cores": config.get("xml_extracted_retroarch_cores", []),
                            "emulator_variables": config.get("emulator_variables", _get_base_emulator_variables()),
                        }
                        
                        with open(config_path, 'w', encoding='utf-8') as file:
                            json.dump(data_to_save, file, ensure_ascii=False, indent=4)
                    except Exception:
                        pass 
            else:
                new_cmd = f'{custom_emu_path} "%ROM%"'
            
            self.result_command = new_cmd.strip()
            self.destroy()
            return

        if is_retro:
            selected_core = self.selected_core_path
            if not selected_core:
                messagebox.showwarning("警告", "请选择一个核心文件。")
                return
            
            core_var = details["core_var"]
            core_path = f'"{core_var}/{selected_core}"'
            cmd = f'{path} -L {core_path} "%ROM%"'
        else:
            cmd = f'{path} "%ROM%"'
        
        self.result_command = cmd
        self.destroy()


class CustomAskStringDialog(ctk.CTkToplevel):
    def __init__(self, master, title, prompt):
        super().__init__(master)
        self.title(title)
        self.prompt = prompt
        self.result: Optional[str] = None
        self.transient(master)
        self.grab_set()
        
        self.label = ctk.CTkLabel(self, text=self.prompt)
        self.label.pack(padx=20, pady=(10, 0))
        
        self.entry = ctk.CTkEntry(self, width=300)
        self.entry.pack(padx=20, pady=(5, 10))
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda event: self.ok())
        
        self.ok_button = ctk.CTkButton(self, text="确定", command=self.ok)
        self.ok_button.pack(padx=20, pady=(0, 10))
        
        self.master.wait_window(self)

    def ok(self):
        self.result = self.entry.get().strip()
        self.destroy()

    @staticmethod
    def ask_string(title, prompt, parent):
        dialog = CustomAskStringDialog(parent, title, prompt)
        return dialog.result


class SystemsEditorFrame(BaseInterface):
    @staticmethod
    def get_title() -> str:
        return "系统配置编辑器"
        
    @staticmethod
    def get_order() -> int:
        return 20

    def __init__(self, master: Any, app_ref: Any, **kwargs):
        super().__init__(master, app_ref, **kwargs)
        self.systems_base_path: Optional[Path] = None
        self.systems_file_path: Optional[Path] = None
        self.xml_tree: Optional[ET.ElementTree] = None
        self.systems_data: Dict[str, ET.Element] = {} 
        self.current_system_element: Optional[ET.Element] = None
        self.current_command_element: Optional[ET.Element] = None
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.status_var = ctk.StringVar(value="状态: 未加载配置文件")
        self.system_fullname_var = ctk.StringVar()
        self.system_path_var = ctk.StringVar()
        self.system_extension_var = ctk.StringVar()
        self.system_platform_var = ctk.StringVar()
        self.command_label_var = ctk.StringVar()
        self.command_string_var = ctk.StringVar()

        initial_os = "windows".capitalize()
        self.target_os_var = ctk.StringVar(value=initial_os)
        self._last_processed_os = initial_os.lower()
        
    def create_ui(self):
        self.top_controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_controls_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.top_controls_frame.grid_columnconfigure(0, weight=1)

        status_os_frame = ctk.CTkFrame(self.top_controls_frame, fg_color="transparent")
        status_os_frame.grid(row=0, column=0, sticky="ew")
        status_os_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(status_os_frame, textvariable=self.status_var, anchor="w").grid(row=0, column=0, padx=5, sticky="ew")
        ctk.CTkLabel(status_os_frame, text="目标操作系统:", anchor="e").grid(row=0, column=1, padx=(10, 5), sticky="e")
        self.os_option_menu = ctk.CTkOptionMenu(
            status_os_frame, 
            values=[os_name.capitalize() for os_name in OS_OPTIONS],
            command=self._on_os_change,
            variable=self.target_os_var,
            width=100
        )
        self.os_option_menu.grid(row=0, column=2, padx=(0, 5), sticky="e")

        controls_buttons_frame = ctk.CTkFrame(self.top_controls_frame, fg_color="transparent")
        controls_buttons_frame.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(controls_buttons_frame, text="保存配置", command=self.save_config, width=90, fg_color="#3498DB").pack(side="left", padx=5)
        ctk.CTkButton(controls_buttons_frame, text="手动选择文件", command=self._manual_select_file, width=120).pack(side="left", padx=5)
        ctk.CTkButton(controls_buttons_frame, text="备份/还原", command=self.open_backup_restore, width=100, fg_color="#F39C12").pack(side="left", padx=5)

        self.editor_area = ctk.CTkFrame(self)
        self.editor_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.editor_area.grid_columnconfigure((0, 1), weight=1)
        self.editor_area.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self.editor_area)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text="系统列表:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.sys_list = CTkListFrame(left, self, 'system', fg_color=LIST_FRAME_BG_COLOR)
        self.sys_list.grid(row=1, column=0, sticky="nsew", pady=5)

        sys_btns = ctk.CTkFrame(left)
        sys_btns.grid(row=2, column=0, sticky="ew")
        sys_btns.columnconfigure((0, 1), weight=1)
        ctk.CTkButton(sys_btns, text="新增系统", command=self.add_new_system, fg_color="#27AE60").grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(sys_btns, text="删除选中", command=self.del_selected_system, fg_color="#E74C3C").grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        right = ctk.CTkFrame(self.editor_area)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        right.grid_rowconfigure(4, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="系统详细信息 (System Details):", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        sys_dtl_frame = ctk.CTkFrame(right)
        sys_dtl_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        sys_dtl_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(sys_dtl_frame, text="显示名称 (Fullname):", width=140).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        e_fullname = ctk.CTkEntry(sys_dtl_frame, textvariable=self.system_fullname_var)
        e_fullname.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        e_fullname.bind("<FocusOut>", lambda e: self._do_update_sys('fullname'))

        ctk.CTkLabel(sys_dtl_frame, text="路径 (Path):", width=140).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        e_path = ctk.CTkEntry(sys_dtl_frame, textvariable=self.system_path_var)
        e_path.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        e_path.bind("<FocusOut>", lambda e: self._do_update_sys('path'))

        ctk.CTkLabel(sys_dtl_frame, text="扩展名 (Extension):", width=140).grid(row=2, column=0, padx=5, pady=2, sticky="w")
        e_ext = ctk.CTkEntry(sys_dtl_frame, textvariable=self.system_extension_var)
        e_ext.grid(row=2, column=1, padx=5, pady=2, sticky="ew")
        e_ext.bind("<FocusOut>", lambda e: self._do_update_sys('extension'))
        
        ctk.CTkLabel(sys_dtl_frame, text="平台/主题 (Platform/Theme):", width=140).grid(row=3, column=0, padx=5, pady=2, sticky="w")
        e_platform = ctk.CTkEntry(sys_dtl_frame, textvariable=self.system_platform_var)
        e_platform.grid(row=3, column=1, padx=5, pady=2, sticky="ew")
        e_platform.bind("<FocusOut>", lambda e: self._do_update_sys_platform_theme())


        ctk.CTkLabel(right, text="模拟器/命令 (Emulator/Command):", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=(10, 5))

        cmd_dtl_frame = ctk.CTkFrame(right)
        cmd_dtl_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        cmd_dtl_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(cmd_dtl_frame, text="配置名 (Label):", width=140).grid(row=0, column=0, padx=5, pady=2, sticky="w")
        e_label = ctk.CTkEntry(cmd_dtl_frame, textvariable=self.command_label_var)
        e_label.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        e_label.bind("<FocusOut>", lambda e: self._do_update_cmd_label())

        ctk.CTkButton(cmd_dtl_frame, text="自定义命令", command=self.custom_emu, width=120).grid(row=0, column=2, padx=5, pady=2)

        ctk.CTkLabel(cmd_dtl_frame, text="配置代码 (Cmd):", width=140).grid(row=1, column=0, padx=5, pady=2, sticky="w")
        e_cmd = ctk.CTkEntry(cmd_dtl_frame, textvariable=self.command_string_var)
        e_cmd.grid(row=1, column=1, padx=5, pady=2, sticky="ew", columnspan=2)
        e_cmd.bind("<FocusOut>", lambda e: self._do_update())

        self.cmd_list = CTkListFrame(right, self, 'command', fg_color=LIST_FRAME_BG_COLOR)
        self.cmd_list.grid(row=4, column=0, sticky="nsew", pady=5)

        cmd_btns = ctk.CTkFrame(right)
        cmd_btns.grid(row=5, column=0, sticky="ew")
        cmd_btns.columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(cmd_btns, text="添加", command=self.add_cmd, fg_color="#27AE60").grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(cmd_btns, text="删除", command=self.del_cmd, fg_color="#E74C3C").grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(cmd_btns, text="说明", command=self.show_instruction, fg_color="#F39C12").grid(row=0, column=2, padx=(5, 0), sticky="ew")
        
        self._reload_config()

    def _set_var_safe(self, var: ctk.StringVar, value: str):
        if var.get() != value:
            var.set(value)

    def _get_systems_file_path(self, target_os_lower: str) -> Optional[Path]:
        if not self.systems_base_path or not self.systems_base_path.is_dir():
            return None
        return self.systems_base_path / target_os_lower / SYSTEMS_FILES[0]

    def _on_os_change(self, selected_os_display: str):
        selected_os = selected_os_display.lower()
        current_os_for_check = self._last_processed_os
        if current_os_for_check == selected_os:
            return
        
        self._last_processed_os = selected_os
        new_systems_file_path = self._get_systems_file_path(selected_os)

        load_or_create_emu_config(target_os=selected_os, systems_file_path=new_systems_file_path)

        if new_systems_file_path and new_systems_file_path.is_file():
            self.load_config(new_systems_file_path)
            messagebox.showinfo("提示", f"目标操作系统已切换为 {selected_os_display}，并已自动加载对应的 Systems 文件。")
        else:
            self._clear_all_data()
            self._update_status_display()
            messagebox.showwarning("警告", f"目标操作系统已切换为 {selected_os_display}，但未找到对应的 Systems 文件，请手动选择或创建。")

    def load_config(self, file_path: Path):
        tree = load_systems_file(file_path)
        
        if tree:
            self.systems_file_path = file_path
            self.xml_tree = tree
            self._clear_system_details()
            self._process_xml()
            self._refresh_sys_list()
        else:
            self._clear_all_data()

    def _clear_all_data(self):
        self.systems_file_path = None
        self.xml_tree = None
        self.systems_data = {}
        self.current_system_element = None
        self.current_command_element = None
        self._clear_system_details()
        self.sys_list.update_list({})
        self.cmd_list.update_list({})
        
    def _reload_config(self):
        config = load_app_config_systems()
        self._last_processed_os = config[TARGET_OS_KEY] or "windows"
        self.target_os_var.set(self._last_processed_os.capitalize())

        load_or_create_emu_config(target_os=self._last_processed_os)

        esde_root = config.get("esde_root_path")
        if esde_root and esde_root.is_dir():
            self.systems_base_path = esde_root / ES_DE_SYSTEMS_SUBPATH
            systems_file = self._get_systems_file_path(self._last_processed_os)
            if systems_file and systems_file.is_file():
                load_or_create_emu_config(target_os=self._last_processed_os, systems_file_path=systems_file)
                self.load_config(systems_file)
        
        self._update_status_display()

    def _process_xml(self):
        if self.xml_tree is None:
            return
        
        self.systems_data = {}
        for system_element in self.xml_tree.getroot().findall('system'):
            fullname = system_element.findtext('fullname')
            if fullname:
                self.systems_data[fullname] = system_element

    def _refresh_sys_list(self, reselect_key: Optional[str] = None):
        display_data = {}
        for fullname, element in self.systems_data.items():
            display_name = fullname 
            display_data[fullname] = display_name
            
        self.sys_list.update_list(display_data, reselect_key=reselect_key)

    def _clear_system_details(self):
        self._set_var_safe(self.system_fullname_var, "")
        self._set_var_safe(self.system_path_var, "")
        self._set_var_safe(self.system_extension_var, "")
        self._set_var_safe(self.system_platform_var, "")
        self._set_var_safe(self.command_label_var, "")
        self._set_var_safe(self.command_string_var, "")
        self.cmd_list.update_list({})

    def listbox_selected(self, key: Optional[str], list_id: str):
        if list_id == 'system':
            self.current_command_element = None
            self._set_var_safe(self.command_label_var, "")
            self._set_var_safe(self.command_string_var, "")
            
            if key:
                self.current_system_element = self.systems_data.get(key)
                if self.current_system_element:
                    self._set_var_safe(self.system_fullname_var, self.current_system_element.findtext('fullname') or "")
                    self._set_var_safe(self.system_path_var, self.current_system_element.findtext('path') or "")
                    self._set_var_safe(self.system_extension_var, self.current_system_element.findtext('extension') or "")
                    
                    platform_text = self.current_system_element.findtext('platform') or ""
                    theme_text = self.current_system_element.findtext('theme') or ""
                    if platform_text == theme_text:
                        self._set_var_safe(self.system_platform_var, platform_text)
                    elif theme_text:
                        self._set_var_safe(self.system_platform_var, f"{platform_text} / {theme_text}")
                    else:
                        self._set_var_safe(self.system_platform_var, platform_text)

                    self._refresh_cmd_list()
                else:
                    self.current_system_element = None
                    self._clear_system_details()
            else:
                self.current_system_element = None
                self._clear_system_details()
            
        elif list_id == 'command':
            if self.current_system_element:
                for command_element in self.current_system_element.findall('command'):
                    label = command_element.get('label')
                    if label == key:
                        self.current_command_element = command_element
                        self._set_var_safe(self.command_label_var, label or "")
                        self._set_var_safe(self.command_string_var, command_element.text or "")
                        return
            
            self.current_command_element = None
            self._set_var_safe(self.command_label_var, "")
            self._set_var_safe(self.command_string_var, "")

    def _do_update_cmd_label(self):
        if self.current_command_element is None or not self.xml_tree or self.current_system_element is None:
            return
        
        new_label = self.command_label_var.get()
        old_label = self.current_command_element.get('label')

        if new_label and new_label != old_label:
            for cmd in self.current_system_element.findall('command'):
                if cmd is not self.current_command_element and cmd.get('label') == new_label:
                    messagebox.showwarning("警告", "模拟器名称 (Label) 已存在，请使用唯一名称。")
                    self._set_var_safe(self.command_label_var, old_label or '')
                    return
            
            self.current_command_element.set('label', new_label)
            self._refresh_cmd_list(reselect_key=new_label)

    def _do_update(self):
        if self.current_command_element is None or not self.xml_tree:
            return
        new_text = self.command_string_var.get()
        old_text = self.current_command_element.text
        if new_text != old_text:
            self.current_command_element.text = new_text

    def _do_update_sys(self, tag: str):
        if self.current_system_element is None or not self.xml_tree:
            return
        
        var_map = {
            'fullname': self.system_fullname_var,
            'path': self.system_path_var,
            'extension': self.system_extension_var,
        }
        new_text = var_map[tag].get()
        element = self.current_system_element.find(tag)

        if element is None:
            if new_text:
                new_element = ET.Element(tag)
                new_element.text = new_text
                self.current_system_element.append(new_element)
        else:
            if new_text:
                element.text = new_text
            else:
                self.current_system_element.remove(element)
                
        if tag == 'fullname':
            old_fullname = self.sys_list.selected_key
            if new_text and new_text != old_fullname and old_fullname in self.systems_data:
                temp_element = self.systems_data.pop(old_fullname)
                self.systems_data[new_text] = temp_element
                self._refresh_sys_list(reselect_key=new_text)

    def _do_update_sys_platform_theme(self):
        if self.current_system_element is None or not self.xml_tree:
            return
            
        new_text = self.system_platform_var.get()
        parts = [p.strip() for p in new_text.split('/')]
        platform_text = parts[0] if parts else ''
        theme_text = parts[1] if len(parts) > 1 else platform_text

        platform_elem = self.current_system_element.find('platform')
        if platform_elem is None:
            if platform_text:
                platform_elem = ET.Element('platform')
                platform_elem.text = platform_text
                self.current_system_element.append(platform_elem)
        else:
            if platform_text:
                platform_elem.text = platform_text
            else:
                self.current_system_element.remove(platform_elem)

        theme_elem = self.current_system_element.find('theme')
        if theme_elem is None:
            if theme_text:
                theme_elem = ET.Element('theme')
                theme_elem.text = theme_text
                self.current_system_element.append(theme_elem)
        else:
            if theme_text:
                theme_elem.text = theme_text
            else:
                self.current_system_element.remove(theme_elem)
                
        self._refresh_sys_list(reselect_key=self.sys_list.selected_key)

    def del_selected_system(self):
        selected_key = self.sys_list.selected_key
        if not selected_key:
            messagebox.showwarning("警告", "请先从左侧列表选择一个系统才能删除。")
            return

        element_to_delete = self.systems_data.get(selected_key)
        if element_to_delete is None or not self.xml_tree:
            messagebox.showerror("错误", "找不到选中的系统元素。")
            return

        if not messagebox.askyesno("确认删除", f"确定永久删除系统配置 '{self.sys_list.data.get(selected_key, selected_key)}' 吗?"):
            return
            
        try:
            self.xml_tree.getroot().remove(element_to_delete)
            if selected_key in self.systems_data:
                del self.systems_data[selected_key]
                
            messagebox.showinfo("成功", f"系统 '{self.sys_list.data.get(selected_key, selected_key)}' 已删除。请记得保存配置。")
            self.current_system_element = None
            self.current_command_element = None
            self._clear_system_details()
            self._refresh_sys_list()
        except Exception as e:
            messagebox.showerror("删除失败", f"删除系统时发生错误: {e}")

    def add_new_system(self):
        if self.xml_tree is None:
            messagebox.showwarning("警告", "请先加载或手动创建一个 Systems 文件。")
            return

        l = CustomAskStringDialog.ask_string(
            "新增系统", 
            "请输入新的系统全称 (Fullname):", 
            parent=self
        )
        if not l:
            return
        
        if l in self.systems_data:
            messagebox.showerror("错误", "该系统全称已存在。")
            return
        
        new_system = ET.Element('system')
        
        ET.SubElement(new_system, 'fullname').text = l
        ET.SubElement(new_system, 'path').text = "%ROMPATH%"
        ET.SubElement(new_system, 'extension').text = ".zip .7z .iso"
        ET.SubElement(new_system, 'platform').text = l
        ET.SubElement(new_system, 'theme').text = l
        
        default_cmd_label = "default"
        default_cmd_text = "%EMULATOR_DEFAULT% %ROM%"
        ET.SubElement(new_system, 'command', label=default_cmd_label).text = default_cmd_text

        self.xml_tree.getroot().append(new_system)
        self.systems_data[l] = new_system 
        self._refresh_sys_list(reselect_key=l)
        messagebox.showinfo("成功", f"系统 '{l}' 已添加。请在右侧编辑详情并保存。")

    def add_cmd(self):
        if self.current_system_element is None:
            messagebox.showwarning("警告", "请先选择一个系统才能添加模拟器。")
            return

        l = CustomAskStringDialog.ask_string(
            "新建模拟器", 
            "请输入模拟器名称 (Label, 例如: RetroArch_New):", 
            parent=self
        )
        if not l:
            return
        
        for cmd in self.current_system_element.findall('command'):
            if cmd.get('label') == l:
                messagebox.showerror("错误", "该模拟器名称已存在。")
                return
        
        c = "%EMULATOR_DEFAULT% %ROM%"
        n = ET.Element('command', label=l)
        n.text = c
        self.current_system_element.append(n)
        self._refresh_cmd_list(reselect_key=l)
        messagebox.showinfo("成功", f"模拟器 '{l}' 已添加。请在配置代码框中编辑详情并保存。")

    def del_cmd(self):
        if self.current_command_element is None or self.current_system_element is None:
            messagebox.showwarning("警告", "请先从命令列表选择一个模拟器才能删除。")
            return

        current_label = self.command_label_var.get()
        if not messagebox.askyesno("确认删除", f"确定删除模拟器 '{current_label}' 吗?"):
            return
            
        try:
            self.current_system_element.remove(self.current_command_element)
            self._set_var_safe(self.command_label_var, "")
            self._set_var_safe(self.command_string_var, "")
            self.current_command_element = None
            self._refresh_cmd_list()
            messagebox.showinfo("成功", f"模拟器 '{current_label}' 已删除。")
        except Exception as e:
            messagebox.showerror("删除失败", f"删除模拟器时发生错误: {e}")

    def _refresh_cmd_list(self, reselect_key: Optional[str] = None):
        if self.current_system_element is None:
            self.cmd_list.update_list({})
            return
            
        cmd_data = {}
        for command_element in self.current_system_element.findall('command'):
            label = command_element.get('label')
            if label:
                cmd_data[label] = command_element
                
        self.cmd_list.update_list({k: k for k in cmd_data.keys()}, reselect_key=reselect_key)

    def _update_status_display(self):
        status = "状态: 未加载配置文件"
        if self.systems_file_path:
            status = f"状态: 已加载 {self.systems_file_path.name} ({len(self.systems_data)} 个系统)"
        self.status_var.set(status)
        
    def open_backup_restore(self):
        if not self.systems_file_path or not self.systems_file_path.is_file():
            messagebox.showwarning("警告", "请先加载或手动选择一个 Systems 文件才能使用备份/还原功能。")
            return

        BackupRestoreWindow(self, self.app_ref, self)

    def show_instruction(self):
        messagebox.showinfo("说明", SYSTEMS_INSTRUCTION_CONTENT)

    def custom_emu(self):
        if self.current_system_element is None or self.current_command_element is None:
            messagebox.showwarning("警告", "请先选择一个系统和模拟器配置。")
            return

        dialog = BasicCommandSelector(self)
        
        if dialog.result_command:
            self._set_var_safe(self.command_string_var, dialog.result_command)
            self._do_update()
            messagebox.showinfo("提示", "命令已生成并更新到配置代码框。")
            
    def _manual_select_file(self):
        
        if hasattr(self.app_ref, 'config_manager'):
            initial_dir = self.app_ref.config_manager.systems_dir_path
        else:
            initial_dir = None
        
        selected_file_path = filedialog.askopenfilename(
            title="选择 ES-DE Systems 配置文件", 
            filetypes=[("ES-DE Systems XML", "es_systems*.xml"), ("All Files", "*.*")],
            initialdir=initial_dir if initial_dir and initial_dir.is_dir() else Path.home()
        )
        
        if not selected_file_path:
            return

        selected_file_path = Path(selected_file_path)
        new_os = self._last_processed_os

        if selected_file_path.name.lower() in [s.lower() for s in SYSTEMS_FILES]:
            parent_dir = selected_file_path.parent
            if parent_dir and parent_dir.name.lower() in OS_OPTIONS:
                self.systems_base_path = parent_dir.parent
                new_os = parent_dir.name.lower()
                
                load_or_create_emu_config(target_os=new_os, systems_file_path=selected_file_path)
                self.load_config(selected_file_path)
                
                if new_os != self._last_processed_os:
                    self._last_processed_os = new_os
                    self.target_os_var.set(new_os.capitalize())

            else:
                messagebox.showwarning("警告", "手动选择的文件路径不符合【基础路径/操作系统名/es_systems.xml】的结构，基础路径将被清除。")
                self.systems_base_path = None
                load_or_create_emu_config(target_os=new_os, systems_file_path=selected_file_path)
                self.load_config(selected_file_path) 
        
        else:
            messagebox.showwarning("警告", "选择的文件名不是 'es_systems.xml'，基础路径将被清除。")
            self.systems_base_path = None
            load_or_create_emu_config(target_os=new_os, systems_file_path=selected_file_path)
            self.load_config(selected_file_path) 
        
        self._update_status_display()

    def save_config(self):
        if self.systems_file_path and self.xml_tree:
            save_systems_file(self.systems_file_path, self.xml_tree)
        else:
            messagebox.showwarning("保存失败", "系统文件路径无效。请先加载或手动选择文件。")

register_interface(SystemsEditorFrame.get_title(), SystemsEditorFrame.get_order(), SystemsEditorFrame)