import customtkinter as ctk
from typing import Any, Optional, Dict, List, Tuple, Union
import xml.etree.ElementTree as ET
import io
import sys
import json
import os
from pathlib import Path 
from tkinter import messagebox, filedialog 
import platform

from base_interface import BaseInterface 
from interface_loader import register_interface 
    
INTERFACE_TITLE = "模拟器路径编辑器" 
INTERFACE_ORDER = 25 
__version__ = "0.1.1" 

CONFIG_FILE_NAME = "esde_toolkit_config.json"
SYSTEMS_FILE_CONFIG_KEY = "systems_config_file_found_path"
FIND_RULES_FILE_NAME = "es_find_rules.xml"
CONFIG_DIR_NAME = "config"
OS_OPTIONS = ["windows", "unix", "macos", "linux", "haiku", "android"] 

def _get_config_file_path(filename: str) -> Path:
    try:
        script_dir = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))).resolve()
    except NameError:
        script_dir = Path(os.getcwd())
    
    config_dir = script_dir / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True) 
    return config_dir / filename

def _get_find_rules_file_path(target_os: str) -> Optional[Path]:
    config_path = _get_config_file_path(CONFIG_FILE_NAME)
    
    if not config_path.is_file():
        return None
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            systems_path_str = data.get(SYSTEMS_FILE_CONFIG_KEY)
            
            if systems_path_str and systems_path_str.lower() != 'none':
                systems_path = Path(systems_path_str)
                
                base_dir = systems_path.parent.parent 
                
                find_rules_dir = base_dir / target_os.lower()
                find_rules_path = find_rules_dir / FIND_RULES_FILE_NAME
                
                return find_rules_path
                
    except Exception as e:
        print(f"路径解析错误: {e}", file=sys.stderr)
        
    return None

class XmlRuleEditor:

    def __init__(self, file_path: Optional[Path]):
        self.file_path = file_path
        self.tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        
    def set_file_path(self, new_path: Optional[Path]):
        self.file_path = new_path
        self.tree = None
        self.root = None
        
    def load_from_file(self) -> bool:
        if not self.file_path or not self.file_path.is_file():
            self.root = None
            self.tree = None
            return False
            
        try:
            xml_content = self.file_path.read_text(encoding='utf-8')
            content_cleaned = xml_content.replace(' xmlns="http://www.emulationstation.org/xml/system"', '')
            
            self.tree = ET.parse(io.StringIO(content_cleaned))
            self.root = self.tree.getroot()
            return True
        except Exception as e:
            print(f"错误: 无法加载或解析 Find Rules XML 文件: {e}", file=sys.stderr)
            self.root = None
            self.tree = None
            return False

    def get_all_rules_keys(self) -> List[Tuple[str, str, str]]:
        if self.root is None: return []
        keys_data = []
        for element in self.root:
            if element.tag in ['emulator', 'core']:
                name = element.get('name')
                tag_type = element.tag.capitalize()
                
                lookup_key = f"{name} ({tag_type})" 
                
                rule_element = element.find('rule')
                rule_type = rule_element.get('type') if rule_element is not None and rule_element.get('type') else "staticpath" 
                
                display_text = f"{name} ({tag_type}) [{rule_type}]"
                
                keys_data.append((rule_type, display_text, lookup_key))
        return keys_data

    def _find_rule_elements(self, key: str) -> List[ET.Element]:
        if self.root is None: return []
        name, tag_type = key.rsplit(' ', 1)
        tag = tag_type.strip('()').lower()
        
        elements = [e for e in self.root if e.tag == tag and e.get('name') == name]
        return elements

    def get_paths_for_key(self, key: str) -> List[str]:
        elements = self._find_rule_elements(key)
        paths = []
        for element in elements:
            for rule in element.findall('rule'):
                for entry in rule.findall('entry'):
                    if entry.text:
                        paths.append(entry.text.strip())
        return paths

    def update_paths(self, key: str, new_paths: List[str]):
        if not key or self.root is None:
            return

        elements = self._find_rule_elements(key)
        
        for element in elements:
            rule = element.find('rule') 
            if rule is None:
                rule = ET.SubElement(element, 'rule', type='staticpath')
                
            for entry in rule.findall('entry'):
                rule.remove(entry)
            
            for path in new_paths:
                if path and path.strip():
                    new_entry = ET.SubElement(rule, 'entry')
                    new_entry.text = path.strip()
                    
    def save_to_file(self) -> bool:
        if not self.file_path or self.tree is None:
            messagebox.showerror("保存失败", "文件路径无效或XML未加载。")
            return False
        
        try:
            self.tree.write(self.file_path, encoding='utf-8', xml_declaration=True)
            return True
        except Exception as e:
            print(f"错误: 无法保存 XML 文件: {e}", file=sys.stderr)
            return False
        
class SystemsListEditorPlugin(BaseInterface):

    def __init__(self, master: Any, app_ref: Any, **kwargs):
        super().__init__(master, app_ref, **kwargs)
        
        default_os = platform.system().lower()
        if default_os not in OS_OPTIONS:
            default_os = "windows"
            
        self.target_os_var = ctk.StringVar(value=default_os.capitalize())
        
        self.editor = XmlRuleEditor(None)
        self.is_loaded = False
        
        self.current_selected_key = None
        self.path_entries: List[Dict[str, Union[ctk.CTkFrame, ctk.CTkEntry]]] = [] 

        self.grid_rowconfigure(0, weight=0) 
        self.grid_rowconfigure(1, weight=1) 
        self.grid_columnconfigure(0, weight=1)

    @staticmethod
    def get_title() -> str:
        return INTERFACE_TITLE

    @staticmethod
    def get_order() -> int:
        return INTERFACE_ORDER

    def _open_file_dialog(self, entry_widget: ctk.CTkEntry):
        
        initial_dir = Path.home()
        current_path = entry_widget.get().strip()
        
        try:
            expanded_path = Path(os.path.expandvars(current_path))
            if expanded_path.is_file(): 
                initial_dir = expanded_path.parent
            elif expanded_path.is_dir(): 
                initial_dir = expanded_path
        except Exception:
            pass 
            
        selected_dir = filedialog.askdirectory(
            title="步骤 1/2: 选择模拟器所在的目录",
            initialdir=initial_dir
        )
        
        if not selected_dir:
            return 

        choice = messagebox.askyesno(
            "选择文件或目录", 
            f"您已选择目录：\n{selected_dir}\n\n是否要继续选择此目录中的一个可执行文件？\n\n选择【是】: 打开文件选择器。\n选择【否】: 使用目录路径作为最终路径。"
        )
        
        final_path = selected_dir
        
        if choice:
            
            current_os = self.target_os_var.get().lower()
            if current_os == "windows":
                filetypes = [
                    ("Windows 可执行文件", "*.exe"),
                    ("所有文件", "*.*")
                ]
            elif current_os == "macos":
                filetypes = [
                    ("macOS 应用程序/可执行文件", "*"),
                    ("所有文件", "*.*")
                ]
            elif current_os in ["linux", "unix", "haiku"]:
                filetypes = [
                    ("Unix-like 可执行文件或脚本", "*"),
                    ("所有文件", "*.*")
                ]
            elif current_os == "android":
                filetypes = [
                    ("Android APK 或脚本", "*.apk *.sh *"),
                    ("所有文件", "*.*")
                ]
            else:
                filetypes = [("所有文件", "*.*")]
                
            selected_file = filedialog.askopenfilename(
                title="步骤 2/2: 选择可执行文件",
                initialdir=selected_dir, 
                filetypes=filetypes 
            )
            
            if selected_file:
                final_path = selected_file
        
        entry_widget.delete(0, 'end')
        entry_widget.insert(0, final_path)

    def _load_config_and_list(self):
        current_os = self.target_os_var.get().lower()
        
        new_path = _get_find_rules_file_path(current_os)
        self.editor.set_file_path(new_path)
        
        self.is_loaded = self.editor.load_from_file()
        
        self._update_status_display()
        self._clear_path_entries() 
        if self.is_loaded:
            self._load_list_view()
        else:
            self._clear_list_view()
            self._disable_controls()
            
    def _on_os_change(self, new_os: str):
        self._load_config_and_list()
        
    def _update_status_display(self):
        find_rules_path = self.editor.file_path
        
        if self.is_loaded:
            status_text = f"状态：✅ 已加载配置文件。路径: {find_rules_path.name}"
            status_color = "green"
            self._enable_controls()
        elif find_rules_path is None:
            status_text = "状态：❌ 错误。未找到 Systems 配置路径。请先在配置设置中设置 ES-DE 根目录。"
            status_color = "red"
            self._disable_controls()
        elif not find_rules_path.is_file():
            status_text = f"状态：⚠️ 警告。文件不存在于目录：{find_rules_path.parent}"
            status_color = "orange"
            self._disable_controls()
        else:
            status_text = "状态：❌ 加载失败。XML 解析错误。"
            status_color = "red"
            self._disable_controls()
            
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=status_text, text_color=status_color)

    def _enable_controls(self):
        if hasattr(self, 'add_path_btn'):
            self.add_path_btn.configure(state="normal")
            self.save_btn.configure(state="normal")
            self.left_frame.configure(label_text="模拟器/核心 列表")
            
    def _disable_controls(self):
        if hasattr(self, 'add_path_btn'):
            self.add_path_btn.configure(state="disabled")
            self.save_btn.configure(state="disabled")
            if hasattr(self, 'right_frame_title'):
                self.right_frame_title.configure(text="请从左侧选择一个项目进行编辑。")
            self.left_frame.configure(label_text="模拟器/核心 列表 (未加载)")

    def create_ui(self):
        top_control_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_control_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top_control_frame.grid_columnconfigure(0, weight=0)
        top_control_frame.grid_columnconfigure(1, weight=0)
        top_control_frame.grid_columnconfigure(2, weight=1)
        top_control_frame.grid_columnconfigure(3, weight=0)
        
        ctk.CTkLabel(top_control_frame, text="目标操作系统:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=(10, 5), sticky="w")
        
        ctk.CTkOptionMenu(top_control_frame, 
                          values=[os.capitalize() for os in OS_OPTIONS], 
                          variable=self.target_os_var, 
                          command=self._on_os_change,
                          width=100).grid(row=0, column=1, padx=(0, 20), sticky="w")

        self.status_label = ctk.CTkLabel(top_control_frame, text="", anchor="w")
        self.status_label.grid(row=0, column=2, sticky="ew", padx=10)
        
        ctk.CTkLabel(top_control_frame, text=f"v{__version__}", font=ctk.CTkFont(size=12)).grid(row=0, column=3, padx=10, sticky="e")
        
        main_grid_frame = ctk.CTkFrame(self)
        main_grid_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        main_grid_frame.grid_columnconfigure(0, weight=1)
        main_grid_frame.grid_columnconfigure(1, weight=3)
        main_grid_frame.grid_rowconfigure(0, weight=1)

        self.left_frame = ctk.CTkScrollableFrame(main_grid_frame, label_text="模拟器/核心 列表")
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        self.left_frame.grid_columnconfigure(0, weight=1)
        
        self.right_frame = ctk.CTkFrame(main_grid_frame)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.right_frame.grid_rowconfigure(1, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)
        
        self.right_frame_title = ctk.CTkLabel(self.right_frame, text="请从左侧选择一个项目进行编辑。", font=ctk.CTkFont(size=18, weight="bold"))
        self.right_frame_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        self.right_frame_path_container = ctk.CTkScrollableFrame(self.right_frame, label_text="默认路径 (Entry) 配置")
        self.right_frame_path_container.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.right_frame_path_container.grid_columnconfigure(0, weight=1)

        bottom_control_frame = ctk.CTkFrame(self.right_frame, height=50, fg_color="transparent")
        bottom_control_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        bottom_control_frame.grid_columnconfigure(0, weight=1)
        bottom_control_frame.grid_columnconfigure(1, weight=1)
        
        self.add_path_btn = ctk.CTkButton(bottom_control_frame, text="➕ 增加新路径", command=self._add_path_entry, state="disabled")
        self.add_path_btn.grid(row=0, column=0, padx=(0, 10), pady=10, sticky="w")
        self.save_btn = ctk.CTkButton(bottom_control_frame, text="💾 保存修改到文件", command=self._save_changes_to_xml, fg_color="green", hover_color="#006400", state="disabled")
        self.save_btn.grid(row=0, column=1, padx=(10, 0), pady=10, sticky="e")
        
        self._load_config_and_list()

    def _clear_list_view(self):
        for widget in self.left_frame.winfo_children():
            widget.destroy()

    def _load_list_view(self):
        if not self.is_loaded: return
        self._clear_list_view()
        
        keys_data = self.editor.get_all_rules_keys()
        
        sorted_keys = sorted(keys_data, key=lambda x: (x[0], x[1]))

        for i, (rule_type, display_text, lookup_key) in enumerate(sorted_keys):
            btn = ctk.CTkButton(self.left_frame, text=display_text, 
                                command=lambda k=lookup_key: self._select_item(k),
                                anchor="w")
            btn.grid(row=i, column=0, sticky="ew", padx=5, pady=2)

    def _select_item(self, key: str):
        self.current_selected_key = key
        self.right_frame_title.configure(text=f"编辑: {key}")
        
        self.add_path_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        
        self._clear_path_entries()
        paths = self.editor.get_paths_for_key(key)
        for path in paths:
            self._add_path_entry(initial_value=path)

    def _clear_path_entries(self):
        for widget in self.right_frame_path_container.winfo_children():
            widget.destroy()
        self.path_entries.clear()

    def _add_path_entry(self, initial_value: str = ""):
        container = self.right_frame_path_container
        index = len(self.path_entries)
        
        entry_frame = ctk.CTkFrame(container, fg_color="transparent")
        entry_frame.grid(row=index, column=0, sticky="ew", padx=5, pady=5)
        entry_frame.grid_columnconfigure(0, weight=1) 
        entry_frame.grid_columnconfigure(1, weight=0) 
        entry_frame.grid_columnconfigure(2, weight=0) 
        
        path_entry = ctk.CTkEntry(entry_frame, placeholder_text="请输入新的路径或使用选择按钮...")
        path_entry.insert(0, initial_value)
        path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        select_btn = ctk.CTkButton(entry_frame, text="📁 选择路径", width=80,
                                   command=lambda e=path_entry: self._open_file_dialog(e))
        select_btn.grid(row=0, column=1, padx=(5, 5), pady=0)
        
        delete_btn = ctk.CTkButton(entry_frame, text="🗑️ 删除", width=60, 
                                   command=lambda f=entry_frame: self._delete_path_entry(f))
        delete_btn.grid(row=0, column=2, padx=(5, 0), pady=0)
        
        self.path_entries.append({'frame': entry_frame, 'entry': path_entry})

    def _delete_path_entry(self, entry_frame: ctk.CTkFrame):
        entry_frame.destroy()
        self.path_entries = [item for item in self.path_entries if item['frame'] != entry_frame]
        
        for i, item in enumerate(self.path_entries):
            item['frame'].grid(row=i, column=0, sticky="ew", padx=5, pady=5)

    def _save_changes_to_xml(self):
        if not self.current_selected_key or not self.is_loaded:
            messagebox.showerror("错误", "XML 文件未加载或未选择项目。")
            return
            
        new_paths = []
        for item in self.path_entries:
            path = item['entry'].get().strip()
            if path:
                new_paths.append(path)

        self.editor.update_paths(self.current_selected_key, new_paths)
        
        if self.editor.save_to_file():
            messagebox.showinfo("保存成功", 
                                f"【{self.current_selected_key}】的配置已更新并保存到文件：{self.editor.file_path.name}")
        else:
            messagebox.showerror("保存失败", "无法将修改写入文件。请检查文件路径和权限。")
            
        self._load_config_and_list() 
        
    def on_switch_to(self):
        self._load_config_and_list()

    def on_switch_away(self):
        pass

    def save_config(self):
        self._save_changes_to_xml()

register_interface(SystemsListEditorPlugin.get_title(), SystemsListEditorPlugin.get_order(), SystemsListEditorPlugin)