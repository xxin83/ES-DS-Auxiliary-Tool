import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
import json 
import os 
import shutil 
import xml.etree.ElementTree as ET 
from datetime import datetime
import subprocess
import zlib 
import sqlite3 
import hashlib 

TOOLKIT_CONFIG_FILE = "esde_toolkit_config.json" 
LIST_BUTTON_HEIGHT = 35
NORMAL_COLOR = "#2A2A2A"  
SELECTED_ROM_COLOR = "#1F6AA5"  
SELECTED_GAME_COLOR = "#A51F6A" 
DEFAULT_EXTENSIONS = [".zip", ".7z", ".nes", ".sfc", ".n64", ".iso", ".cue", ".chd"]

DB_DIR = 'db'
DB_FILENAME = 'rom_master_index.db'
SQLITE_DB_PATH = Path(__file__).parent / DB_DIR / DB_FILENAME 

def _calculate_hashes_internal(rom_path: Path, start_offset: int) -> Dict[str, Optional[str]]:
    BUFFER_SIZE = 65536 
    
    try:
        hash_crc = 0
        hash_md5 = hashlib.md5()
        hash_sha1 = hashlib.sha1()
        
        original_file_size = rom_path.stat().st_size
        size_for_hash = original_file_size - start_offset
        
        with open(rom_path, 'rb') as f:
            if start_offset > 0:
                f.seek(start_offset)
            
            while True:
                data = f.read(BUFFER_SIZE)
                if not data:
                    break
                hash_crc = zlib.crc32(data, hash_crc) & 0xFFFFFFFF
                hash_md5.update(data)
                hash_sha1.update(data)

        calculated_hashes = {
            "CRC": f"{hash_crc:08X}",
            "MD5": hash_md5.hexdigest().upper(),
            "SHA1": hash_sha1.hexdigest().upper(),
            "Size": str(size_for_hash) 
        }
        
        return calculated_hashes
            
    except Exception as e:
        return {"CRC": None, "MD5": None, "SHA1": None, "Size": None}


def _calculate_rom_hashes(rom_path: Path, skip_nes_header: bool = False) -> Dict[str, Optional[str]]:
    
    is_nes = rom_path.suffix.lower() == ".nes"
    file_size = rom_path.stat().st_size
    start_offset = 0
    
    # 仅当明确要求跳过头并且是 NES 文件且文件大小足够时才设置偏移量
    if is_nes and skip_nes_header and file_size > 16:
        start_offset = 16
        
    return _calculate_hashes_internal(rom_path, start_offset)


def _get_game_name_by_identifiers(hashes: Dict[str, Optional[str]], rom_filename: str) -> Optional[str]:
    conn = None
    game_name = None
    
    if not SQLITE_DB_PATH.is_file():
        return None
        
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        crc = hashes.get("CRC")
        md5 = hashes.get("MD5")
        sha1 = hashes.get("SHA1")
        
        if any([crc, md5, sha1]): 
            # 移除了 Size 字段的查询
            sql_query_hash = """
            SELECT GameName FROM RomIndex 
            WHERE CRC = ? OR MD5 = ? OR SHA1 = ? 
            """
            
            cursor.execute(
                sql_query_hash, 
                (crc, md5, sha1) 
            )
            
            result = cursor.fetchone()
            if result:
                conn.close()
                return result[0]
        
        if rom_filename:
            sql_query_name = "SELECT GameName FROM RomIndex WHERE RomFilename = ?"
            cursor.execute(sql_query_name, (rom_filename,))
            result = cursor.fetchone()
            if result:
                conn.close()
                return result[0]
            
    except sqlite3.Error as e:
        pass
        
    finally:
        if conn:
            conn.close()
            
    return None

class ToolkitConfigLoader:
    def __init__(self):
        self.config_dir = Path(__file__).parent / "config"
        self.config_path = self.config_dir / TOOLKIT_CONFIG_FILE 
        self.rom_root_path: Optional[Path] = None
        self.system_map: Dict[str, Path] = {}
        self.gamelist_base_path: Optional[Path] = None 
        self.current_xml_path: Optional[Path] = None 

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.is_file():
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {}

    def load_rom_root(self) -> Optional[Path]:
        config = self._load_config()
        path_str = config.get("rom_files_dir") 
        if path_str:
            self.rom_root_path = Path(path_str).resolve()
            if not self.rom_root_path.is_dir():
                 self.rom_root_path = None
        
        gamelist_base_str = config.get("gamelist_base_dir")
        if gamelist_base_str:
            self.gamelist_base_path = Path(gamelist_base_str).resolve()
        
        return self.rom_root_path

    def scan_systems(self) -> bool:
        if not self.rom_root_path or not self.rom_root_path.is_dir():
            self.system_map.clear()
            return False
        self.system_map.clear()
        for system_dir in self.rom_root_path.iterdir():
            if system_dir.is_dir(): 
                self.system_map[system_dir.name] = system_dir
        return bool(self.system_map)
    
    def get_system_names(self) -> List[str]:
        return sorted(list(self.system_map.keys()))

    def get_rom_files_in_system(self, system_name: str, allowed_extensions: List[str]) -> List[Path]:
        system_path = self.system_map.get(system_name)
        if not system_path or not system_path.is_dir(): return []
        allowed_extensions_set = {ext.lower() for ext in allowed_extensions}
        rom_files = []
        for file_path in system_path.rglob('*'): 
            if file_path.is_file() and file_path.suffix.lower() in allowed_extensions_set:
                rom_files.append(file_path)
        return sorted(rom_files, key=lambda p: p.name)

    def _find_gamelist_path(self, system_name: str) -> Union[Path, None]:
        if self.gamelist_base_path:
            gamelist_path = self.gamelist_base_path / system_name / "gamelist.xml"
            if gamelist_path.is_file():
                self.current_xml_path = gamelist_path 
                return gamelist_path
        self.current_xml_path = None
        return None

    def load_gamelist_xml(self, system_name: str) -> Tuple[Optional[ET.Element], Dict[str, Dict[str, Any]]]:
        gamelist_path = self._find_gamelist_path(system_name) 
        if not gamelist_path:
            return None, self._create_empty_gamelist_structure()
        try:
            tree = ET.parse(gamelist_path)
            root = tree.getroot()
            game_entries = {}
            index = 0
            for element in root.findall('game') + root.findall('folder'):
                path_element = element.find('path')
                path_value = path_element.text.strip() if path_element is not None and path_element.text else 'N/A'
                name_element = element.find('name')
                name_value = name_element.text.strip() if name_element is not None and name_element.text else 'Unknown Game'
                entry_key = f"ENTRY_{index}"
                index += 1
                game_entries[entry_key] = {
                    "name": name_value,
                    "path_in_xml": path_value,
                    "type": element.tag,
                    "element": element 
                }
            return root, dict(sorted(game_entries.items(), key=lambda item: item[1]["name"]))
        except ET.ParseError:
            self.current_xml_path = None
            return None, {"XML_PARSE_ERROR": {"name": "错误：gamelist.xml 文件解析失败，可能格式错误。", "path": gamelist_path.as_posix()}}
        except Exception as e:
            self.current_xml_path = None
            return None, {"LOAD_ERROR": {"name": f"加载错误: {str(e)}", "path": gamelist_path.as_posix()}}

    def _create_empty_gamelist_structure(self) -> Dict[str, Dict[str, str]]:
        return {"XML_NOT_FOUND": {"name": "未找到 gamelist.xml。请使用 '导入 ROM' 创建新文件。", "path": "N/A"}}


try:
    from interface_loader import register_interface 
except ImportError:
    def register_interface(*args, **kwargs): pass
    
class RomListPlugin(ctk.CTkFrame):
    
    @staticmethod
    def get_title() -> str:
        return "ROM文件列表生成"

    @staticmethod
    def get_order() -> int:
        return 60 

    def __init__(self, master, app_ref, **kwargs):
        super().__init__(master, **kwargs)
        self.app_ref = app_ref 
        self.toolkit_loader = ToolkitConfigLoader() 
        
        self.rom_files: Dict[str, Path] = {} 
        self.rom_list_widgets: Dict[str, ctk.CTkButton] = {} 
        self.selected_rom_button: Optional[ctk.CTkButton] = None 
        
        self.system_select_var = ctk.StringVar(value="等待加载 ROM 目录...")
        self.current_system_name: Optional[str] = None 
        self.current_xml_root: Optional[ET.Element] = None 
        
        self.game_entry_map: Dict[str, Dict[str, Any]] = {} 
        self.game_list_widgets: Dict[str, ctk.CTkButton] = {}
        self.selected_game_button: Optional[ctk.CTkButton] = None
        
        self.selected_extensions: List[str] = DEFAULT_EXTENSIONS 
        self.extension_button_var = ctk.StringVar(value=f"后缀名 ({len(self.selected_extensions)})")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=250) 
        self.grid_columnconfigure(1, weight=1)
        
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_rowconfigure(1, weight=1) 
        left_frame.grid_columnconfigure(0, weight=1)
        
        self._create_config_controls_left(left_frame)
        self._create_rom_list_frame(left_frame) 

        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        right_frame.grid_rowconfigure(1, weight=1) 
        right_frame.grid_columnconfigure(0, weight=1)

        self._create_game_list_frame(right_frame)
        self._create_list_actions_footer(right_frame) 
        
        self.status_label = ctk.CTkLabel(self, text="状态: 准备就绪", text_color="#3498DB", anchor="w")
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))


    def _create_config_controls_left(self, master_frame: ctk.CTkFrame):
        frame = ctk.CTkFrame(master_frame, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 5))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=0)

        ctk.CTkLabel(frame, text="系统选择:", anchor="w").grid(row=0, column=0, sticky="w", padx=0, pady=(0, 0))
        
        self.system_select_menu = ctk.CTkOptionMenu(
            frame, variable=self.system_select_var, values=["等待加载 ROM 目录..."],
            command=self._on_system_select, dynamic_resizing=True 
        )
        self.system_select_menu.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 5))
        
        self.ext_select_button = ctk.CTkButton(
            frame, textvariable=self.extension_button_var, command=self._open_extension_selector, width=100
        )
        self.ext_select_button.grid(row=1, column=1, sticky="e", padx=0, pady=(0, 5))
        
    def _create_rom_list_frame(self, master_frame: ctk.CTkFrame):
        self.rom_list_scroll_frame = ctk.CTkScrollableFrame( 
            master_frame, label_text="ROM 文件列表 (文件系统)", fg_color="#242424", border_width=0
        )
        self.rom_list_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10)) 
        self.rom_list_scroll_frame.columnconfigure(0, weight=1)

    def _create_game_list_frame(self, master_frame: ctk.CTkFrame):
        ctk.CTkLabel(master_frame, text="游戏目录列表 (gamelist.xml 条目)", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 5)
        )
        
        self.game_list_scroll_frame = ctk.CTkScrollableFrame(
            master_frame, label_text="请先选择系统"
        )
        self.game_list_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 5))
        self.game_list_scroll_frame.columnconfigure(0, weight=1)

    def _create_list_actions_footer(self, master_frame: ctk.CTkFrame):
        
        row1 = ctk.CTkFrame(master_frame, fg_color="transparent")
        row1.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 5))
        row1.columnconfigure(0, weight=1)
        
        btn_get_name = ctk.CTkButton(
            row1, text="开始 DB 查询 (获取游戏名)", command=self._open_get_game_name_dialog, fg_color="#3498DB"
        )
        btn_get_name.grid(row=0, column=0, sticky="ew")

        row2 = ctk.CTkFrame(master_frame, fg_color="transparent")
        row2.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)
        
        btn_import = ctk.CTkButton(
            row2, text="导入 ROM", command=self._import_roms_to_gamelist, fg_color="#2980B9"
        )
        btn_import.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        btn_save = ctk.CTkButton(
            row2, text="保存", command=self._open_backup_manager_dialog, fg_color="#F39C12"
        )
        btn_save.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _open_get_game_name_dialog(self):
        if not self.current_system_name:
            self._update_status("请先选择一个系统。", "red")
            messagebox.showwarning("操作警告", "请先选择一个系统。")
            return
        
        self._perform_db_query_and_update()

    def _perform_db_query_and_update(self): 
        
        if not SQLITE_DB_PATH.is_file():
            self._update_status(f"错误：未找到数据库文件 {SQLITE_DB_PATH.name}。", "red")
            messagebox.showerror("数据库错误", f"未找到数据库文件: {SQLITE_DB_PATH.as_posix()}")
            return
            
        if not self.rom_files:
            self._update_status("ROM 文件列表为空，无法进行查询。", "orange")
            messagebox.showwarning("操作警告", "ROM 文件列表为空。")
            return
        
        if not self.game_entry_map or list(self.game_entry_map.keys())[0].startswith(("XML_", "LOAD_")):
            self._update_status("游戏目录列表为空，请先使用 '导入 ROM'。", "orange")
            messagebox.showwarning("操作警告", "游戏目录列表为空，请先导入 ROM。")
            return

        newly_updated_count = 0
        rom_items = list(self.rom_files.items()) 
        total_roms = len(rom_items)
        game_keys = list(self.game_entry_map.keys()) 
        
        for i, (rom_filename, rom_path) in enumerate(rom_items):
            self._update_status(f"查询进度: {i+1}/{total_roms} - 正在处理 {rom_filename} (使用本地 DB)...", "#3498DB")
            self.update_idletasks() 
            
            is_nes = rom_path.suffix.lower() == ".nes"
            game_name = None
            
            # --- 步骤 1: 尝试 iNES Header Skip 方式 (仅限 NES) ---
            if is_nes:
                # 尝试跳过 16 字节头
                hashes = _calculate_rom_hashes(rom_path, skip_nes_header=True)
                game_name = _get_game_name_by_identifiers(hashes, rom_filename) 
                
                # --- 步骤 2: 如果是 NES 文件且未找到，则尝试不跳过 16 字节 ---
                if not game_name:
                    self._update_status(f"查询进度: {i+1}/{total_roms} - {rom_filename} (跳过 header 未命中，尝试完整文件)...", "orange")
                    # 尝试完整文件
                    hashes = _calculate_rom_hashes(rom_path, skip_nes_header=False)
                    game_name = _get_game_name_by_identifiers(hashes, rom_filename)
            else:
                # --- 非 NES 文件，直接使用完整文件进行哈希计算 (即不跳过) ---
                hashes = _calculate_rom_hashes(rom_path, skip_nes_header=False)
                game_name = _get_game_name_by_identifiers(hashes, rom_filename)
            
            if game_name:
                
                match_found = False
                for entry_key in game_keys:
                    entry = self.game_entry_map[entry_key]
                    path_in_xml = Path(entry.get('path_in_xml', "")).name
                    
                    if path_in_xml == rom_filename:
                        if entry['name'] != game_name:
                            entry['name'] = game_name 
                            
                            game_element: ET.Element = entry['element']
                            name_element = game_element.find('name')
                            if name_element is None:
                                name_element = ET.SubElement(game_element, 'name')
                            name_element.text = game_name
                            
                            newly_updated_count += 1
                            match_found = True
                        break

            
        if newly_updated_count > 0:
            self._load_games_list(self.current_system_name, force_reload_data=False) 
            self._update_status(f"查询完成，成功更新了 {newly_updated_count} 个游戏名称。请点击 '保存' 按钮。", "#27AE60")
        else:
            self._update_status("查询完成，没有找到或更新任何游戏名称。", "orange")

    def _open_extension_selector(self):
        for widget in self.winfo_children():
            if isinstance(widget, ExtensionSelectorDialog):
                widget.lift()
                return

        ext_dialog = ExtensionSelectorDialog(self, self.selected_extensions)
        ext_dialog.grab_set()

    def _on_extensions_applied(self, new_extensions: List[str]):
        
        new_extensions = [ext.lower() for ext in new_extensions if ext.startswith(".")]
        
        if not new_extensions:
            new_extensions = DEFAULT_EXTENSIONS 
            self._update_status("警告：未选择任何有效后缀，已重置为默认后缀。", "orange")
            
        self.selected_extensions = new_extensions
        self.extension_button_var.set(f"后缀名 ({len(self.selected_extensions)})")
        
        if self.current_system_name:
            self._load_rom_list(self.current_system_name)
            self._update_status(f"ROM 后缀已更新，共 {len(self.selected_extensions)} 种。已刷新 ROM 列表。", "#2ECC71")
        else:
            self._update_status(f"ROM 后缀已更新，共 {len(self.selected_extensions)} 种。", "#2ECC71")

    def _load_games_list(self, system_name: str, force_reload_data: bool = True):
        for widget in self.game_list_scroll_frame.winfo_children():
            widget.destroy()
        self.game_list_widgets.clear()
        self.selected_game_button = None
        
        if force_reload_data:
            self.game_entry_map.clear()
            self.current_xml_root, self.game_entry_map = self.toolkit_loader.load_gamelist_xml(system_name)

        game_keys = list(self.game_entry_map.keys())
        displayable_entries = [key for key in game_keys if not key.startswith(("XML_", "LOAD_"))]

        has_error = not displayable_entries and (game_keys and game_keys[0].startswith(("XML_", "LOAD_")))

        if self.current_xml_root is None: 
            self.current_xml_root = ET.Element('gameList')
                 
        if has_error: 
            error_key = game_keys[0] if game_keys else "NO_ENTRIES"
            error_data = self.game_entry_map.get(error_key, {"name": "gamelist.xml 中没有游戏条目。", "path": "N/A"})

            initial_label = ctk.CTkLabel(
                self.game_list_scroll_frame, 
                text=error_data['name'], 
                text_color="red" if "ERROR" in error_key or "NOT_FOUND" in error_key else "gray"
            )
            initial_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=50)
            self.game_list_scroll_frame.configure(label_text=f"系统 '{system_name}' 游戏目录 (0 个条目)")
            return

        for i, entry_key in enumerate(displayable_entries):
            entry_data = self.game_entry_map[entry_key]
            
            # 保持右侧列表简洁，只显示名称和类型
            display_text = f"[{entry_data['type'].upper()}] {entry_data['name']}"
            
            btn = ctk.CTkButton(
                self.game_list_scroll_frame, 
                text=display_text, 
                height=LIST_BUTTON_HEIGHT,
                fg_color=NORMAL_COLOR,
                command=lambda key=entry_key: self._on_game_select(key),
                anchor="w"
            )
            btn.grid(row=i, column=0, sticky="ew", padx=5, pady=(2, 2))
            self.game_list_widgets[entry_key] = btn

        self.game_list_scroll_frame.configure(label_text=f"系统 '{system_name}' 游戏目录 ({len(displayable_entries)} 个条目)")
        

    def _highlight_matching_game(self, rom_filename: str):
        for btn in self.game_list_widgets.values():
            if btn.cget("fg_color") != SELECTED_GAME_COLOR: 
                btn.configure(fg_color=NORMAL_COLOR)
                
        self.selected_game_button = None

        match_found = False
        for entry_key, entry_data in self.game_entry_map.items():
            path_in_xml = entry_data.get('path_in_xml', "")
            if Path(path_in_xml).name == rom_filename:
                btn = self.game_list_widgets.get(entry_key)
                if btn:
                    btn.configure(fg_color=SELECTED_ROM_COLOR)
                    self.selected_game_button = btn
                    match_found = True
                    break 
        
        if not match_found:
             self._update_status(f"ROM: {rom_filename} 在 gamelist.xml 中没有匹配条目。", "orange")

    def _on_game_select(self, entry_key: str):
        for key, btn in self.game_list_widgets.items():
            if btn.cget("fg_color") != SELECTED_ROM_COLOR: 
                 btn.configure(fg_color=NORMAL_COLOR)

        new_button = self.game_list_widgets[entry_key]
        new_button.configure(fg_color=SELECTED_GAME_COLOR)
        self.selected_game_button = new_button
        
        entry_data = self.game_entry_map.get(entry_key, {})
        raw_path = entry_data.get("path_in_xml", "N/A")
        
        if raw_path and raw_path != 'N/A':
            rom_filename_display = Path(raw_path).name 
        else:
            rom_filename_display = "未关联 ROM 文件"
            
        self._update_status(f"已选中游戏目录条目，关联 ROM 文件: {rom_filename_display}", SELECTED_GAME_COLOR)

    
    def _load_rom_list(self, system_name: str):
        
        for widget in self.rom_list_scroll_frame.winfo_children():
            widget.destroy()
        self.rom_list_widgets.clear()
        self.selected_rom_button = None
        self.rom_files.clear() 
        
        rom_paths = self.toolkit_loader.get_rom_files_in_system(
            system_name, 
            self.selected_extensions
        )

        if not rom_paths:
            self.rom_list_scroll_frame.configure(label_text=f"ROM 文件列表 ({system_name}, 0 个文件)")
            return

        for i, rom_path in enumerate(rom_paths):
            display_name = rom_path.name
            
            # 使用文件名作为 key，完整 Path 作为 value
            self.rom_files[display_name] = rom_path
            
            btn = ctk.CTkButton(
                self.rom_list_scroll_frame, 
                text=display_name, 
                height=LIST_BUTTON_HEIGHT,
                fg_color=NORMAL_COLOR,
                command=lambda name=display_name: self._on_rom_select(name), 
                anchor="w"
            )
            btn.grid(row=i, column=0, sticky="ew", padx=5, pady=(2, 2))
            self.rom_list_widgets[display_name] = btn

        self.rom_list_scroll_frame.configure(label_text=f"ROM 文件列表 ({system_name}, {len(rom_paths)} 个文件)")

        if rom_paths:
             self._on_rom_select(rom_paths[0].name) 

    def _on_rom_select(self, rom_name: str): 
        if self.selected_rom_button:
            self.selected_rom_button.configure(fg_color=NORMAL_COLOR)
            
        new_button = self.rom_list_widgets[rom_name]
        new_button.configure(fg_color=SELECTED_ROM_COLOR)
        self.selected_rom_button = new_button
        
        self._highlight_matching_game(rom_name)
        self._update_status(f"已选中 ROM: {rom_name}，并高亮右侧匹配游戏。", SELECTED_ROM_COLOR)

    def _import_roms_to_gamelist(self):
        if not self.current_system_name:
            self._update_status("请先选择一个系统。", "red")
            return
            
        if not self.rom_files:
            self._update_status("ROM 文件列表为空，无法导入。", "orange")
            return
            
        if self.current_xml_root is None:
            self.current_xml_root = ET.Element('gameList')
            
        existing_rom_filenames = {
            Path(data['path_in_xml']).name
            for data in self.game_entry_map.values()
            if data.get('path_in_xml')
        }
        
        # 获取系统 ROM 目录的 Path 对象
        system_path = self.toolkit_loader.system_map.get(self.current_system_name)
        if not system_path:
            self._update_status(f"错误：无法获取系统 '{self.current_system_name}' 的 ROM 路径，导入失败。", "red")
            return

        new_entries_count = 0
        new_game_entries = {}
        
        for rom_filename, rom_path in self.rom_files.items():
            
            if rom_filename not in existing_rom_filenames:
                
                # --- 关键修改：计算相对于系统目录的路径 ---
                try:
                    # 1. 计算相对路径 (e.g., subdir/game.sfc)
                    relative_path = rom_path.relative_to(system_path) 
                    # 2. 格式化为 XML 所需的路径 (e.g., ./subdir/game.sfc)
                    xml_path_value = f"./{relative_path.as_posix()}" 
                except ValueError as e:
                    self._update_status(f"路径计算错误: {rom_path.name} 不在系统目录中。跳过。", "orange")
                    continue
                # ----------------------------------------
                
                game_element = ET.SubElement(self.current_xml_root, 'game')
                
                path_element = ET.SubElement(game_element, 'path')
                path_element.text = xml_path_value # 使用正确的相对路径
                
                name_element = ET.SubElement(game_element, 'name')
                name_element.text = rom_path.stem
                
                entry_key = f"ENTRY_{len(self.game_entry_map) + new_entries_count}"
                new_game_entries[entry_key] = {
                    "name": rom_path.stem,
                    "path_in_xml": xml_path_value, # 存储正确的路径
                    "type": "game",
                    "element": game_element
                }
                new_entries_count += 1
                existing_rom_filenames.add(rom_filename) 
        
        if new_entries_count > 0:
            
            game_keys = list(self.game_entry_map.keys())
            if game_keys and game_keys[0].startswith(("XML_", "LOAD_", "NO_ENTRIES")):
                self.game_entry_map.clear()

            self.game_entry_map.update(new_game_entries)
            self._load_games_list(self.current_system_name, force_reload_data=False) 
            self._update_status(f"成功导入 {new_entries_count} 个新 ROM 文件。请点击 '保存' 进行保存。", "#27AE60")
        else:
            self._update_status("没有新的 ROM 文件需要导入（已全部重复）。", "orange")
            
    def _execute_save(self, create_backup: bool = False):
        xml_path = self.toolkit_loader.current_xml_path
        
        if not self.current_system_name:
            self._update_status("系统状态错误，无法保存。", "red")
            return
            
        if not xml_path:
            if not self.toolkit_loader.gamelist_base_path:
                 self._update_status("Gamelist Base 目录未设置，无法保存。请检查配置文件。", "red")
                 return
            
            system_dir = self.toolkit_loader.gamelist_base_path / self.current_system_name
            xml_path = system_dir / "gamelist.xml"
            self.toolkit_loader.current_xml_path = xml_path

        if self.current_xml_root is None:
             self.current_xml_root = ET.Element('gameList')

        if create_backup:
            self._create_backup_file(xml_path) 
             
        try:
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            
            tree = ET.ElementTree(self.current_xml_root)
            tree.write(xml_path, encoding='utf-8', xml_declaration=True)
            
            self._update_status(f"列表已成功保存到: {xml_path.as_posix()}", "#27AE60")
        
        except Exception as e:
             self._update_status(f"保存列表失败: {e}", "red")

    def _create_backup_file(self, xml_path: Path):
        if not xml_path.is_file():
            self._update_status("gamelist.xml 尚不存在，跳过备份步骤。", "orange")
            return
            
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        backup_name = f"{xml_path.stem}_{timestamp}.bak"
        backup_path = xml_path.parent / backup_name
        
        try:
            shutil.copy2(xml_path, backup_path)
            self._update_status(f"已创建备份: {backup_name}", "#F39C12")
            return True
        except Exception as e:
            self._update_status(f"备份失败: {e}", "red")
            return False

    def _open_backup_manager_dialog(self):
        if not self.current_system_name:
            messagebox.showerror("错误", "请先选择一个系统来保存。")
            return
            
        expected_path = (self.toolkit_loader.gamelist_base_path / self.current_system_name / "gamelist.xml") if self.toolkit_loader.gamelist_base_path else None
        
        if not expected_path:
             messagebox.showerror("错误", "Gamelist Base 目录未设置，无法进行保存和管理。请检查配置文件。")
             return

        backup_window = BackupManagerDialog(self, expected_path, self.toolkit_loader.current_xml_path)
        backup_window.grab_set()

    def on_switch_to(self):
        rom_root = self.toolkit_loader.load_rom_root()
        
        if rom_root and rom_root.is_dir():
            self._scan_and_load_systems(rom_root)
        else:
            self._update_status("错误：ROM 根目录未在配置文件中设置或路径无效。", "red")
            self.system_select_var.set("未设置 ROM 目录")
            
    # ----------------------------------------------------
    # 【修复】添加空的 on_switch_away 方法以满足主框架要求
    # ----------------------------------------------------
    def on_switch_away(self):
        pass

    def _scan_and_load_systems(self, rom_root: Path):
        if self.toolkit_loader.scan_systems():
            system_names = self.toolkit_loader.get_system_names()
            self.system_select_menu.configure(values=system_names)
            
            first_system = system_names[0]
            self.system_select_var.set(first_system)
            self._on_system_select(first_system)
            self._update_status(f"ROM 根目录已设置，找到 {len(system_names)} 个系统。", "#2ECC71")
        else:
            self._update_status("未找到任何系统子目录。", "orange")
            self.system_select_menu.configure(values=["未找到系统"])
            self.system_select_var.set("未找到系统")
            self._clear_lists()

    def _on_system_select(self, system_name: str):
        self.current_system_name = system_name
        
        if system_name and system_name not in ["等待加载 ROM 目录...", "未设置 ROM 目录", "未找到系统"]:
            self._update_status(f"已选择系统: {system_name}，正在加载数据...", "blue")
            
            self._load_rom_list(system_name) 
            self._load_games_list(system_name, force_reload_data=True) 
            
            rom_count = len(self.rom_files)
            game_count = len([k for k in self.game_entry_map.keys() if not k.startswith(("XML_", "LOAD_"))])
            self._update_status(f"成功加载 {rom_count} 个 ROM 文件和 {game_count} 个游戏目录。", "#2ECC71")

        else:
            self._update_status("请选择一个有效的系统目录。", "orange")
            self._clear_lists()

    def _clear_lists(self):
        for widget in self.rom_list_scroll_frame.winfo_children():
            widget.destroy()
        self.rom_list_widgets.clear()
        self.rom_files.clear()
        self.selected_rom_button = None
        self.rom_list_scroll_frame.configure(label_text="ROM 文件列表 (文件系统)")
        
        self.game_entry_map.clear()
        self.current_xml_root = None
        self.toolkit_loader.current_xml_path = None
        self.selected_game_button = None
        
        for widget in self.game_list_scroll_frame.winfo_children():
            widget.destroy()
        self.game_list_scroll_frame.configure(label_text="请先选择系统")

    def _update_status(self, message: str, color: str = "white"):
        self.status_label.configure(text=f"状态: {message}", text_color=color)
        self.update_idletasks()


class ExtensionSelectorDialog(ctk.CTkToplevel):
    
    STANDARD_EXTENSIONS = [
        ".zip", ".7z", ".rar", ".gz", ".7zip",
        ".nes", ".sfc", ".n64", ".gba", ".gbc", ".gb",
        ".iso", ".cue", ".chd", ".ccd", ".m3u", ".rvz",
        ".bin", ".rom", ".sms", ".md"
    ]

    def __init__(self, master, current_extensions: List[str]):
        super().__init__(master)
        self.master_plugin: RomListPlugin = master
        self.title("选择 ROM 文件后缀名")
        self.geometry("400x550")
        self.transient(master)
        self.resizable(False, False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1) 
        self.grid_rowconfigure(1, weight=0) 

        self.current_extensions = {ext.lower(): ext for ext in current_extensions}
        self.checkbox_vars: Dict[str, tk.IntVar] = {}
        
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1) 
        main_frame.grid_rowconfigure(1, weight=0) 
        main_frame.grid_rowconfigure(2, weight=0) 

        std_frame = ctk.CTkScrollableFrame(main_frame, label_text="标准/常用后缀名 (勾选)")
        std_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10), padx=5)
        std_frame.columnconfigure((0, 1), weight=1) 

        for i, ext in enumerate(self.STANDARD_EXTENSIONS):
            ext_lower = ext.lower()
            var = tk.IntVar(value=1 if ext_lower in self.current_extensions else 0) 
            self.checkbox_vars[ext_lower] = var
            cb = ctk.CTkCheckBox(
                std_frame, text=ext, variable=var, 
                onvalue=1, offvalue=0, 
            )
            col = i % 2
            row = i // 2
            cb.grid(row=row, column=col, sticky="w", padx=10, pady=5)

        ctk.CTkLabel(main_frame, text="自定义后缀名 (用逗号、空格或分号分隔)", anchor="w", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, sticky="w", padx=10, pady=(10, 0)
        )
        
        custom_frame = ctk.CTkFrame(main_frame) 
        custom_frame.grid(row=2, column=0, sticky="ew", pady=(5, 10), padx=5)
        custom_frame.columnconfigure(0, weight=1)

        standard_set = {ext.lower() for ext in self.STANDARD_EXTENSIONS}
        custom_only_exts = [
            ext for ext in self.current_extensions.keys() 
            if ext not in standard_set
        ]
        
        initial_custom_text = ", ".join(custom_only_exts)
        self.custom_entry = ctk.CTkEntry(custom_frame, placeholder_text=".new, .custom, ...", width=350)
        self.custom_entry.insert(0, initial_custom_text)
        self.custom_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        footer_frame.columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            footer_frame, text="应用并刷新", command=self._apply_selection, fg_color="#2ECC71"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        ctk.CTkButton(
            footer_frame, text="取消", command=self.destroy, fg_color="#E74C3C"
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _parse_custom_extensions(self, custom_text: str) -> List[str]:
        valid_custom_exts = []
        if not custom_text:
            return valid_custom_exts

        parts = [p.strip() for p in custom_text.replace(',', ' ').replace(';', ' ').split()]
        
        for part in parts:
            if part.startswith('.') and len(part) > 1:
                valid_custom_exts.append(part.lower())
            elif part and not part.startswith('.'):
                valid_custom_exts.append('.' + part.lower())
        
        return list(set(valid_custom_exts)) 

    def _apply_selection(self):
        selected_exts = set()

        for ext, var in self.checkbox_vars.items():
            if var.get() == 1:
                selected_exts.add(ext.lower())
                
        custom_text = self.custom_entry.get()
        custom_list = self._parse_custom_extensions(custom_text)
        for ext in custom_list:
            selected_exts.add(ext)

        new_extensions = sorted(list(selected_exts))

        if not new_extensions:
            messagebox.showwarning("警告", "您没有选择任何后缀名，请至少选择或输入一个后缀名。")
            return

        self.master_plugin._on_extensions_applied(new_extensions)
        self.destroy()


class SaveBackupDialog(ctk.CTkToplevel):
    def __init__(self, master, current_xml_path: Optional[Path]):
        super().__init__(master)
        self.master_plugin: RomListPlugin = master
        is_file_exist = current_xml_path and current_xml_path.is_file()
        self.title("保存游戏列表 - 备份确认")
        self.geometry("450x220")
        self.transient(master) 
        self.resizable(False, False)
        self.grid_columnconfigure(0, weight=1)
        if is_file_exist:
            prompt_text = "保存前是否需要创建当前的 gamelist.xml 备份？"
            save_text = "确认保存并备份"
            skip_text = "跳过备份并保存"
        else:
            prompt_text = "gamelist.xml 文件不存在。将创建新文件并保存。"
            save_text = "创建并保存新文件"
            skip_text = "取消"
        ctk.CTkLabel(self, text="⚠️ 安全操作确认", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=(15, 5))
        ctk.CTkLabel(self, text=prompt_text, wraplength=400).grid(row=1, column=0, pady=(5, 20))
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, pady=(0, 15), padx=20, sticky="ew")
        button_frame.columnconfigure((0, 1, 2), weight=1)
        if is_file_exist:
            ctk.CTkButton(button_frame, text=save_text, command=self._save_with_backup, fg_color="#27AE60",
                hover_color="#2ECC71").grid(row=0, column=0, padx=(0, 5), sticky="ew")
            ctk.CTkButton(button_frame, text=skip_text, command=self._save_without_backup, fg_color="#2980B9",
                hover_color="#3498DB").grid(row=0, column=1, padx=5, sticky="ew")
            ctk.CTkButton(button_frame, text="取消", command=self.destroy, fg_color="#E74C3C",
                hover_color="#C0392B").grid(row=0, column=2, padx=(5, 0), sticky="ew")
        else:
            ctk.CTkButton(button_frame, text=save_text, command=self._save_without_backup, fg_color="#27AE60",
                hover_color="#2ECC71").grid(row=0, column=0, columnspan=2, padx=(0, 5), sticky="ew")
            ctk.CTkButton(button_frame, text=skip_text, command=self.destroy, fg_color="#E74C3C",
                hover_color="#C0392B").grid(row=0, column=2, padx=(5, 0), sticky="ew")
    def _save_with_backup(self):
        self.master_plugin._execute_save(create_backup=True)
        self.destroy()
    def _save_without_backup(self):
        self.master_plugin._execute_save(create_backup=False)
        self.destroy()

class BackupManagerDialog(ctk.CTkToplevel):
    def __init__(self, master, expected_xml_path: Path, current_xml_path: Optional[Path]):
        super().__init__(master)
        self.title("游戏列表备份管理")
        self.geometry("500x400")
        self.transient(master) 
        self.master_plugin: RomListPlugin = master
        self.xml_path = expected_xml_path
        self.current_xml_path = current_xml_path
        self.backup_dir = self.xml_path.parent
        self.backup_files: List[Path] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"管理文件: {self.xml_path.name} (位于 {self.backup_dir.name})", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        self.backup_list_frame = ctk.CTkScrollableFrame(self, label_text="现有备份文件")
        self.backup_list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.backup_list_frame.columnconfigure(0, weight=1)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        footer.columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(footer, text="手动创建当前备份", command=self._create_manual_backup, 
            fg_color="#F39C12", state=tk.NORMAL if self.xml_path.is_file() else tk.DISABLED).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(footer, text="保存列表", command=self._open_save_backup_dialog, fg_color="#27AE60",
            hover_color="#2ECC71").grid(row=0, column=1, sticky="ew", padx=5)
        ctk.CTkButton(footer, text="取消", command=self.destroy, fg_color="#E74C3C").grid(row=0, column=2, sticky="ew", padx=(5, 0))
        self._load_backup_files()
    def _load_backup_files(self):
        for widget in self.backup_list_frame.winfo_children(): widget.destroy()
        self.backup_files.clear()
        pattern = f"{self.xml_path.stem}_*.bak"
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.backup_files = sorted(list(self.backup_dir.glob(pattern)),key=os.path.getmtime,reverse=True)
        except Exception as e:
            ctk.CTkLabel(self.backup_list_frame, text=f"扫描备份失败: {e}", text_color="red").grid(row=0, column=0, padx=10, pady=10)
            return
        if not self.backup_files:
            ctk.CTkLabel(self.backup_list_frame, text="无现有备份文件。").grid(row=0, column=0, padx=10, pady=10)
            return
        for i, path in enumerate(self.backup_files):
            timestamp_parts = path.stem.split('_')
            timestamp_str = timestamp_parts[-1] if len(timestamp_parts) > 1 else path.name
            try:
                dt = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
                display_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                display_time = path.name 
            frame = ctk.CTkFrame(self.backup_list_frame, fg_color=NORMAL_COLOR)
            frame.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
            frame.columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=display_time, anchor="w").grid(row=0, column=0, sticky="w", padx=10)
            ctk.CTkButton(frame, text="还原", width=60, fg_color="#3498DB",
                command=lambda p=path: self._restore_backup(p)).grid(row=0, column=1, padx=5, pady=5)
            ctk.CTkButton(frame, text="删除", width=60, fg_color="#E74C3C",
                command=lambda p=path: self._delete_backup(p)).grid(row=0, column=2, padx=5, pady=5)
    def _open_save_backup_dialog(self):
        self.destroy() 
        dialog = SaveBackupDialog(self.master_plugin, self.current_xml_path)
        dialog.grab_set()
    def _create_manual_backup(self):
        if not self.xml_path.is_file():
            messagebox.showerror("错误", "gamelist.xml 文件不存在，无法手动备份。请先保存列表。")
            return
        if self.master_plugin._create_backup_file(self.xml_path):
            self._load_backup_files()
        else:
            messagebox.showerror("备份失败", "未能创建备份文件，请检查权限。")
    def _restore_backup(self, backup_path: Path):
        if messagebox.askyesno("确认还原", f"您确定要使用 {backup_path.name} 覆盖当前的 gamelist.xml 吗？此操作不可逆！"):
            try:
                shutil.copy2(backup_path, self.xml_path) 
                self.master_plugin._update_status(f"成功从 {backup_path.name} 还原。", "#3498DB")
                self.master_plugin.toolkit_loader.current_xml_path = self.xml_path 
                self.master_plugin._load_games_list(self.master_plugin.current_system_name, force_reload_data=True) 
                self._load_backup_files()
            except Exception as e:
                messagebox.showerror("还原失败", f"无法还原文件: {e}")
    def _delete_backup(self, backup_path: Path):
        if messagebox.askyesno("确认删除", f"""您确定要删除备份文件 {backup_path.name} 吗？"""):
            try:
                backup_path.unlink()
                self.master_plugin._update_status(f"成功删除备份: {backup_path.name}", "#E74C3C")
                self._load_backup_files()
            except Exception as e:
                messagebox.showerror("删除失败", f"无法删除文件: {e}")

try:
    from interface_loader import register_interface
    register_interface(RomListPlugin.get_title(), RomListPlugin.get_order(), RomListPlugin)
except NameError:
    pass