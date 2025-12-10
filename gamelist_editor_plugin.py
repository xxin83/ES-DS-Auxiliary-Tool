import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
import threading
import sys
import os
import json 
import re 
from collections import defaultdict 
import time

from interface_loader import register_interface 

try:
    import requests 
    API_KEY = "9f81b3aae423fac33b51a0c9409b5e78e6dc423af873c6dd2cfcae606bca7ef4"
    API_URL_BY_NAME = "https://api.thegamesdb.net/v1/Games/ByGameName" 
except ImportError:
    print("警告: 无法导入 requests 库。请在命令行运行: pip install requests")
    requests = None 
    API_KEY = None
    API_URL_BY_NAME = None

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    
ITEM_DEFAULT_COLOR = "#2c2c2c"    
ITEM_SELECTED_COLOR = "#3498DB"   
LIST_FRAME_BG_COLOR = "#2a2d2e"   
ES_SETTINGS_FILE = "es_settings.xml" 


class CTkListFrame(ctk.CTkScrollableFrame): 
     
    def __init__(self, master, editor_ref, list_id: str, **kwargs):
        super().__init__(master, **kwargs)
        self.editor_ref = editor_ref
        self.list_id = list_id
        self.data: Dict[str, Any] = {}
        self.selected_key: Optional[str] = None
        self.item_widgets: Dict[str, ctk.CTkFrame] = {} 
        self.checked_vars: Dict[str, tk.BooleanVar] = {} 
        self.grid_columnconfigure(0, weight=1)
        
    def _on_select(self, key: str):
        if self.selected_key and self.selected_key in self.item_widgets:
            old_container = self.item_widgets[self.selected_key]
            old_container.configure(fg_color=ITEM_DEFAULT_COLOR)
            
        if key in self.item_widgets:
            new_container = self.item_widgets[key]
            new_container.configure(fg_color=ITEM_SELECTED_COLOR)
            
        self.selected_key = key
        self.editor_ref.listbox_selected(key, self.list_id)

    def _create_list_item(self, key: str, index: int):
        container = ctk.CTkFrame(self, fg_color=ITEM_DEFAULT_COLOR, corner_radius=4, height=30)
        container.grid(row=index, column=0, sticky="ew", padx=5, pady=1) 
        container.grid_columnconfigure(1, weight=1) 

        check_var = tk.BooleanVar(value=False)
        self.checked_vars[key] = check_var
        checkbox = ctk.CTkCheckBox(container, text="", variable=check_var, width=20, height=20, corner_radius=5)
        checkbox.grid(row=0, column=0, padx=(5, 0), pady=0, sticky="w")
        
        display_name = self.data.get(key, key)
        label = ctk.CTkLabel(container, text=display_name, 
                             text_color="white",
                             height=30, 
                             anchor="w", 
                             padx=10)
        label.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=0)
        
        def select_and_highlight(event, k=key):
            if event.widget != checkbox: 
                self._on_select(k)
        
        container.bind("<Button-1>", select_and_highlight)
        label.bind("<Button-1>", select_and_highlight)
        
        self.item_widgets[key] = container
        
    def update_list(self, data: Dict[str, Any], reselect_key: Optional[str] = None):
        self.data = data
        
        for widget in self.item_widgets.values():
            widget.destroy()
        self.item_widgets.clear()
        self.checked_vars.clear() 
        self.selected_key = None
        
        sorted_keys = sorted(data.keys())
        
        for index, key in enumerate(sorted_keys):
            self._create_list_item(key, index)
            
        if reselect_key and reselect_key in sorted_keys:
            self._on_select(reselect_key)

    def get_checked_keys(self) -> List[str]:
        return [key for key, var in self.checked_vars.items() if var.get()]

class CTkProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, title: str, total_steps: int):
        super().__init__(master)
        self.title(title)
        self.geometry("350x150")
        self.resizable(False, False)
        self.transient(master) 
        
        self.total_steps = total_steps
        self.current_step = 0
        self.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(self, text="准备开始翻译...", font=ctk.CTkFont(weight="bold"))
        self.status_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", mode="determinate")
        self.progress_bar.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.progress_bar.set(0)
        
        self.percent_label = ctk.CTkLabel(self, text="0%")
        self.percent_label.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="e")
        
        self.protocol("WM_DELETE_WINDOW", self.do_nothing) 

    def do_nothing(self):
        pass

    def update_progress(self, current: int, status_text: str):
        self.current_step = current
        percent = (current / self.total_steps) if self.total_steps > 0 else 1.0
        
        self.progress_bar.set(percent)
        self.percent_label.configure(text=f"{int(percent * 100)}%")
        self.status_label.configure(text=status_text)
        self.update_idletasks() 
        
    def close(self):
        self.destroy()

class OneClickTranslateDialog(ctk.CTkToplevel):
    def __init__(self, master, callback):
        super().__init__(master)
        self.title("一键翻译选项")
        self.geometry("320x160")
        self.callback = callback
        
        self.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self, text="请选择一键翻译的目标字段:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=20, pady=10)
        
        self.name_btn = ctk.CTkButton(self, 
                                      text="翻译全部名称 (Name)", 
                                      command=lambda: self._select_and_close('name'),
                                      fg_color="#3498DB")
        self.name_btn.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.desc_btn = ctk.CTkButton(self, 
                                      text="翻译全部描述 (Description)", 
                                      command=lambda: self._select_and_close('desc'),
                                      fg_color="#3498DB")
        self.desc_btn.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        
        self.grab_set() 

    def _select_and_close(self, choice):
        self.grab_release() 
        self.callback(choice)
        self.destroy()

class LocalConfigLoader:
    CONFIG_DIR_NAME = "config"
    CONFIG_FILE_NAME = "esde_toolkit_config.json"

    def __init__(self):
        # 使用 os.path.dirname(os.path.abspath(__file__))
        # 这种方式在打包环境中对__file__的解析通常比单纯的 Path(__file__).parent 更可靠
        base_path = Path(os.path.dirname(os.path.abspath(__file__)))
        self.config_path: Path = base_path / self.CONFIG_DIR_NAME / self.CONFIG_FILE_NAME
        
        self.gamelist_base_dir: Path = Path('.').resolve()
        self.esde_root_path: Path = Path('.').resolve()
        self.config_data: Dict[str, Any] = {}
        self._load_config()

    # _get_config_file_path 方法保持移除状态，因为它已经被集成到 __init__ 中
    
    def _load_config(self):
        # _load_config 方法保持不变，继续使用 self.config_path
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
                
                gamelist_dir_str = self.config_data.get("gamelist_base_dir", str(Path('.').resolve()))
                self.gamelist_base_dir = Path(gamelist_dir_str).resolve()
                
                esde_root_str = self.config_data.get("esde_root_path", str(Path('.').resolve()))
                self.esde_root_path = Path(esde_root_str).resolve()
            
        except Exception:
            pass
        
class GamelistEditorPlugin(ctk.CTkFrame): 

    def __init__(self, master, app_ref, **kwargs): 
        super().__init__(master, **kwargs) 
        self.app_ref = app_ref
        
        local_config = LocalConfigLoader()
        self.gamelist_base_dir: Path = local_config.gamelist_base_dir
        self.esde_root_dir: Path = local_config.esde_root_path
        
        self.available_lists: Dict[str, Path] = {}
        self.selected_system_name_var = ctk.StringVar(value="(未加载列表)")
        self.detail_entries: List[ctk.CTkEntry] = []
        
        self.is_system_selected = False 
        self.system_name = "未选择/自动加载"
        self.system_rom_path = "N/A"
            
        self.xml_tree: Optional[ET.ElementTree] = None
        self.gamelist_path: Optional[Path] = None
        self.games_data: Dict[str, ET.Element] = {} 
        self.current_game_element: Optional[ET.Element] = None
        self.is_updating_ui = False
        self.es_settings_content: Optional[str] = None
        
        self.progress_dialog: Optional[CTkProgressDialog] = None
        
        self.game_name_var = ctk.StringVar()
        self.game_path_var = ctk.StringVar()
        self.game_image_var = ctk.StringVar()
        self.game_video_var = ctk.StringVar()
        self.game_rating_var = ctk.StringVar()
        self.game_releasedate_var = ctk.StringVar()
        self.game_developer_var = ctk.StringVar()
        self.game_publisher_var = ctk.StringVar()
        self.game_genre_var = ctk.StringVar()
        self.game_players_var = ctk.StringVar()
        self.game_playcount_var = ctk.StringVar()
        
        self.api_results_raw_data: Optional[Dict[str, Any]] = None 
        self.api_current_games_list: List[Dict[str, Any]] = [] 
        self.search_query_var = ctk.StringVar(value="") 
        self.api_select_var = ctk.StringVar(value="请先刮削...") 
        
        self.create_ui()
        
    @staticmethod
    def get_title() -> str:
        return "游戏列表编辑器" 

    @staticmethod
    def get_order() -> int:
        return 30 
        
    def create_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        info_frame = ctk.CTkFrame(self)
        info_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 5))
        info_frame.columnconfigure((0,1), weight=1)

        ctk.CTkLabel(info_frame, 
                     text=f"列表基础目录: {self.gamelist_base_dir}", 
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        
        self.rom_path_label = ctk.CTkLabel(info_frame, 
                     text=f"系统 ROM 路径 (Path Tag): {self.system_rom_path}", 
                     font=ctk.CTkFont(size=12, weight="bold"), 
                     text_color="#3498DB")
        self.rom_path_label.grid(row=0, column=1, sticky="e", padx=5, pady=2)
        
        selection_frame = ctk.CTkFrame(self)
        selection_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 5))
        selection_frame.columnconfigure(1, weight=1) 
        
        ctk.CTkLabel(selection_frame, text="选择列表:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        
        self.list_select_menu = ctk.CTkOptionMenu(selection_frame, 
                                                 values=[self.selected_system_name_var.get()], 
                                                 variable=self.selected_system_name_var, 
                                                 command=self._on_list_selected_by_dropdown)
        self.list_select_menu.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        self.load_manual_btn = ctk.CTkButton(selection_frame, text="手动加载 XML", command=self.select_xml_file, fg_color="#3498DB")
        self.load_manual_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")
        
        self.save_btn = ctk.CTkButton(selection_frame, text="保存列表", command=self.save_gamelist, fg_color="green")
        self.save_btn.grid(row=0, column=3, padx=5, pady=5, sticky="e") 
        
        self.one_click_translate_btn = ctk.CTkButton(selection_frame, 
                                                     text="一键翻译", 
                                                     command=self.open_one_click_translate_dialog, 
                                                     fg_color="#E67E22")
        self.one_click_translate_btn.grid(row=0, column=4, padx=5, pady=5, sticky="e") 
        
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(5, 20))
        main_frame.columnconfigure(0, weight=1)  
        main_frame.columnconfigure(1, weight=2)  
        main_frame.rowconfigure(0, weight=1)
        
        list_frame = ctk.CTkFrame(main_frame)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        list_frame.rowconfigure(1, weight=1) 
        list_frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(list_frame, text="游戏列表 (勾选以批量操作)", font=ctk.CTkFont(weight="bold", size=15)).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(5, 5))
        
        self.game_list = CTkListFrame(list_frame, self, 'game', fg_color=LIST_FRAME_BG_COLOR)
        self.game_list.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=(0, 5))

        btn_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        btn_frame.columnconfigure((0, 1), weight=1)
        
        self.add_btn = ctk.CTkButton(btn_frame, text="新建游戏", command=self.add_game, fg_color="#3498DB")
        self.add_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.del_btn = ctk.CTkButton(btn_frame, text="删除游戏", command=self.del_game, fg_color="red") 
        self.del_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.details_frame = ctk.CTkScrollableFrame(main_frame)
        self.details_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        self.details_frame.columnconfigure(1, weight=1)
        self.details_frame.columnconfigure(2, weight=0) 

        row_idx = 0
        ctk.CTkLabel(self.details_frame, text="游戏详情", font=ctk.CTkFont(weight="bold", size=15)).grid(row=row_idx, column=0, columnspan=3, pady=(5, 10))
        row_idx += 1
        
        ctk.CTkLabel(self.details_frame, text="名称 (Name):").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
        name_entry = ctk.CTkEntry(self.details_frame, textvariable=self.game_name_var)
        name_entry.grid(row=row_idx, column=1, sticky="ew", padx=5, pady=2)
        self.detail_entries.append(name_entry)
        
        if TRANSLATOR_AVAILABLE:
            self.translate_name_btn = ctk.CTkButton(self.details_frame, 
                                                    text="译", 
                                                    width=40, 
                                                    command=self.translate_current_game_name, 
                                                    fg_color="#3498DB")
            self.translate_name_btn.grid(row=row_idx, column=2, sticky="e", padx=(0, 5), pady=2)
        row_idx += 1

        def create_detail_row(parent, row, label_text, var):
            ctk.CTkLabel(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=2)
            entry = ctk.CTkEntry(parent, textvariable=var)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=2) 
            self.detail_entries.append(entry) 
            return entry
            
        create_detail_row(self.details_frame, row_idx, "路径 (Path):", self.game_path_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "图片 (Image):", self.game_image_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "视频 (Video):", self.game_video_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "评分 (Rating):", self.game_rating_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "发行日期 (Release Date):", self.game_releasedate_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "开发商 (Developer):", self.game_developer_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "发行商 (Publisher):", self.game_publisher_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "类型 (Genre):", self.game_genre_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "玩家数 (Players):", self.game_players_var)
        row_idx += 1
        create_detail_row(self.details_frame, row_idx, "游玩次数 (Play Count):", self.game_playcount_var)
        row_idx += 1
        
        ctk.CTkLabel(self.details_frame, 
                     text="--- 游戏刮削 (TheGamesDB) ---", 
                     font=ctk.CTkFont(weight="bold", size=15),
                     text_color="#F39C12"
                     ).grid(row=row_idx, column=0, columnspan=3, pady=(15, 5), sticky="ew")
        row_idx += 1
        
        ctk.CTkLabel(self.details_frame, text="刮削搜索名称:").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
        self.search_query_entry = ctk.CTkEntry(
            self.details_frame, 
            textvariable=self.search_query_var,
        )
        self.search_query_entry.grid(row=row_idx, column=1, sticky="ew", padx=5, pady=2)
        
        self.scrape_button = ctk.CTkButton(
            self.details_frame,
            text="开始刮削", 
            command=self._handle_scrape_button_click,
            fg_color="#2ECC71",
            hover_color="#27AE60",
            width=80
        )
        self.scrape_button.grid(row=row_idx, column=2, sticky="e", padx=(0, 5), pady=2)
        row_idx += 1
        
        ctk.CTkLabel(self.details_frame, text="刮削结果选择:").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
        self.api_select_menu = ctk.CTkOptionMenu(
            self.details_frame, 
            variable=self.api_select_var, 
            values=["请先刮削..."],
            command=self._on_api_result_select,
            dynamic_resizing=True
        )
        self.api_select_menu.grid(row=row_idx, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        self.api_select_menu.configure(state="disabled")
        row_idx += 1
        
        ctk.CTkLabel(self.details_frame, text="描述 (Description):").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
        row_idx += 1
        
        self.desc_textbox = ctk.CTkTextbox(self.details_frame, height=150)
        self.desc_textbox.grid(row=row_idx, column=0, columnspan=3, sticky="ew", padx=5, pady=2) 
        self.desc_textbox.bind("<FocusOut>", self._on_desc_changed)
        row_idx += 1
        
        if TRANSLATOR_AVAILABLE:
            self.translate_btn = ctk.CTkButton(self.details_frame, text="翻译描述 (Google)", command=self.translate_desc, fg_color="#3498DB")
            self.translate_btn.grid(row=row_idx, column=0, columnspan=3, padx=5, pady=5, sticky="ew") 
            row_idx += 1

        self._initial_load_settings() 
        self._set_controls_state("disabled")
        
        self.game_name_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_path_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_image_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_video_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_rating_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_releasedate_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_developer_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_publisher_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_genre_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_players_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))
        self.game_playcount_var.trace_add("write", lambda n, i, m: self.after(50, self._do_update))


    def _set_var_safe(self, var: ctk.StringVar, value: str):
        if var.get() != value:
            self.is_updating_ui = True
            var.set(value)
            self.is_updating_ui = False
            
    def _on_desc_changed(self, event):
        if self.is_updating_ui or self.current_game_element is None:
            return
        
        new_text = self.desc_textbox.get("1.0", "end-1c").strip()
        self._update_xml_tag(self.current_game_element, 'desc', new_text)

    def _do_update(self):
        if self.is_updating_ui or self.current_game_element is None:
            return
            
        updates = {
            'name': self.game_name_var.get(),
            'path': self.game_path_var.get(),
            'image': self.game_image_var.get(),
            'video': self.game_video_var.get(),
            'rating': self.game_rating_var.get(),
            'releasedate': self.game_releasedate_var.get(),
            'developer': self.game_developer_var.get(),
            'publisher': self.game_publisher_var.get(),
            'genre': self.game_genre_var.get(),
            'players': self.game_players_var.get(),
            'playcount': self.game_playcount_var.get(),
        }
        
        for tag, value in updates.items():
            self._update_xml_tag(self.current_game_element, tag, value)
            
        new_name = self.game_name_var.get()
        if new_name and self.current_game_element in self.games_data.values():
            old_key = next((k for k, v in self.games_data.items() if v == self.current_game_element), None)
            
            if old_key and old_key != new_name:
                pass
            
    def _update_xml_tag(self, element: ET.Element, tag: str, value: str):
        child = element.find(tag)
        clean_value = value.strip() if value is not None else ""
        
        if clean_value:
            if child is None:
                new_child = ET.SubElement(element, tag)
                new_child.text = clean_value
            else:
                child.text = clean_value
        else:
            if child is not None:
                element.remove(child)

    def _set_controls_state(self, state: str):
        self.save_btn.configure(state=state)
        self.one_click_translate_btn.configure(state=state) 
        self.del_btn.configure(state=state)
        self.add_btn.configure(state=state)
        
        self.scrape_button.configure(state=state)
        self.search_query_entry.configure(state=state)
        self.api_select_menu.configure(state="disabled") 
        
        for entry in self.detail_entries:
            entry.configure(state=state)

        if self.current_game_element or state == "normal":
            self.desc_textbox.configure(state="normal")
        else:
            self.desc_textbox.configure(state="disabled")
        
        if hasattr(self, 'translate_btn') and TRANSLATOR_AVAILABLE:
            self.translate_btn.configure(state=state)
            self.translate_name_btn.configure(state=state) 

    def _initial_load_settings(self):
        self.available_lists = self._find_available_gamelists()
        
        system_names = sorted(self.available_lists.keys())
        
        if system_names:
            self.list_select_menu.configure(values=system_names)
            first_system = system_names[0]
            self.selected_system_name_var.set(first_system)
            self._on_list_selected_by_dropdown(first_system)
        else:
            self.selected_system_name_var.set("(未找到 gamelist.xml)")
            self.list_select_menu.configure(values=["(未找到 gamelist.xml)"])

    def _find_available_gamelists(self) -> Dict[str, Path]:
        lists = {}
        if not self.gamelist_base_dir.is_dir():
            return lists
            
        for system_dir in self.gamelist_base_dir.iterdir():
            if system_dir.is_dir():
                gamelist_path = system_dir / "gamelist.xml"
                if gamelist_path.is_file():
                    lists[system_dir.name] = gamelist_path
        return lists

    def _on_list_selected_by_dropdown(self, selected_system_name: str):
        if selected_system_name.startswith("(") or selected_system_name == "未选择/自动加载":
            self.is_system_selected = False
            self.game_list.update_list({})
            self._clear_details()
            self._set_controls_state("disabled")
            return

        self.system_name = selected_system_name
        self.gamelist_path = self.available_lists.get(selected_system_name)
        
        if self.gamelist_path and self.gamelist_path.is_file():
            self._load_gamelist(self.gamelist_path)
            self.is_system_selected = True
            self._set_controls_state("normal")
        else:
            messagebox.showerror("错误", f"找不到文件: {selected_system_name}/gamelist.xml")
            self.is_system_selected = False
            self.game_list.update_list({})
            self._clear_details()
            self._set_controls_state("disabled")

    def select_xml_file(self):
        initial_dir = self.gamelist_base_dir if self.gamelist_base_dir.is_dir() else Path('.')
        xml_path = filedialog.askopenfilename(
            initialdir=str(initial_dir),
            title="选择 gamelist.xml 文件",
            filetypes=(("XML files", "*.xml"), ("All files", "*.*"))
        )
        if xml_path:
            self.gamelist_path = Path(xml_path).resolve()
            self.system_name = self.gamelist_path.parent.name
            self.selected_system_name_var.set(f"(手动加载) {self.system_name}")
            self._load_gamelist(self.gamelist_path)
            self.is_system_selected = True
            self._set_controls_state("normal")
    
    def _load_gamelist(self, path: Path):
        self.gamelist_path = path
        self.games_data = {}
        self.current_game_element = None
        self._clear_details()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            xml_content = xml_content.lstrip('\ufeff')
            
            self.xml_tree = ET.ElementTree(ET.fromstring(xml_content))
            root = self.xml_tree.getroot()

            if root.find("path") is not None:
                self.system_rom_path = root.find("path").text.strip()
            else:
                self.system_rom_path = "N/A"
            self.rom_path_label.configure(text=f"系统 ROM 路径 (Path Tag): {self.system_rom_path}")


            for elem in root.findall('./game') + root.findall('./folder'):
                path_tag = elem.find('path')
                key = path_tag.text.strip() if path_tag is not None and path_tag.text else elem.findtext('name', 'Unknown')
                
                original_key = key
                count = 1
                while key in self.games_data:
                    key = f"{original_key}_{count}"
                    count += 1
                
                self.games_data[key] = elem
            
            display_data = {
                key: elem.findtext('name', key) 
                for key, elem in self.games_data.items()
            }
            self.game_list.update_list(display_data)

        except ET.ParseError as e:
            messagebox.showerror("XML 解析错误", f"无法解析 {path.name}: {e}")
            self.game_list.update_list({})
        except Exception as e:
            messagebox.showerror("加载错误", f"加载 {path.name} 时发生错误: {e}")
            self.game_list.update_list({})
            
    def _refresh_gamelist(self, reselect_key: Optional[str] = None):
        if self.xml_tree is None:
             return
             
        new_games_data = {}
        try:
            root = self.xml_tree.getroot()
            
            for elem in root.findall('./game') + root.findall('./folder'):
                path_tag = elem.find('path')
                key = path_tag.text.strip() if path_tag is not None and path_tag.text else elem.findtext('name', 'Unknown')
                original_key = key
                count = 1
                while key in new_games_data:
                    key = f"{original_key}_{count}"
                    count += 1
                new_games_data[key] = elem
                
            self.games_data = new_games_data 
            
            display_data = {
                key: elem.findtext('name', key) 
                for key, elem in self.games_data.items()
            }
            self.game_list.update_list(display_data, reselect_key=reselect_key)

        except Exception as e:
            messagebox.showwarning("刷新警告", f"刷新游戏列表时发生错误: {e}")
            
    def listbox_selected(self, key: str, list_id: str):
        if list_id == 'game':
            elem = self.games_data.get(key)
            self._load_details_from_selection(elem)
            
    def _load_details_from_selection(self, elem: ET.Element):
        self.current_game_element = elem
        self._set_controls_state("normal")
        
        if elem is not None:
            
            self._set_var_safe(self.game_name_var, elem.findtext('name', ''))
            self._set_var_safe(self.game_path_var, elem.findtext('path', ''))
            self._set_var_safe(self.game_image_var, elem.findtext('image', ''))
            self._set_var_safe(self.game_video_var, elem.findtext('video', ''))
            self._set_var_safe(self.game_rating_var, elem.findtext('rating', ''))
            self._set_var_safe(self.game_releasedate_var, elem.findtext('releasedate', ''))
            self._set_var_safe(self.game_developer_var, elem.findtext('developer', ''))
            self._set_var_safe(self.game_publisher_var, elem.findtext('publisher', ''))
            self._set_var_safe(self.game_genre_var, elem.findtext('genre', ''))
            self._set_var_safe(self.game_players_var, elem.findtext('players', ''))
            self._set_var_safe(self.game_playcount_var, elem.findtext('playcount', ''))
            
            desc_text = elem.findtext('desc', '').strip()
            self.is_updating_ui = True
            self.desc_textbox.configure(state="normal")
            self.desc_textbox.delete("1.0", "end")
            self.desc_textbox.insert("1.0", desc_text)
            self.is_updating_ui = False
            
            game_name = elem.findtext('name', '').strip()
            cleaned_name = self._clean_game_name(game_name)
            self.search_query_var.set(cleaned_name)
            self._clear_api_results()

    def _clear_details(self):
        self.current_game_element = None
        self._set_var_safe(self.game_name_var, "")
        self._set_var_safe(self.game_path_var, "")
        self._set_var_safe(self.game_image_var, "")
        self._set_var_safe(self.game_video_var, "")
        self._set_var_safe(self.game_rating_var, "")
        self._set_var_safe(self.game_releasedate_var, "")
        self._set_var_safe(self.game_developer_var, "")
        self._set_var_safe(self.game_publisher_var, "")
        self._set_var_safe(self.game_genre_var, "")
        self._set_var_safe(self.game_players_var, "")
        self._set_var_safe(self.game_playcount_var, "")
        
        self.is_updating_ui = True
        self.desc_textbox.configure(state="normal")
        self.desc_textbox.delete("1.0", "end")
        self.desc_textbox.configure(state="disabled")
        self.is_updating_ui = False
        
        self.search_query_var.set("")
        self._clear_api_results()
        self._set_controls_state("disabled")
        
    def save_gamelist(self):
        if self.xml_tree is None or self.gamelist_path is None:
            messagebox.showwarning("保存警告", "未加载有效的游戏列表。")
            return
            
        try:
            self._on_desc_changed(None)
            self._do_update()
            
            self.xml_tree.write(self.gamelist_path, encoding='utf-8', xml_declaration=True)
            messagebox.showinfo("保存成功", "游戏列表已保存成功！")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存 gamelist.xml 时发生错误: {e}")

    def add_game(self):
        if self.xml_tree is None:
            messagebox.showwarning("警告", "请先加载一个游戏列表。")
            return

        new_name = simpledialog.askstring("新建游戏", "请输入新游戏的名称:")
        if not new_name:
            return

        new_key = new_name
        count = 1
        while new_key in self.games_data:
            new_key = f"{new_name}_{count}"
            count += 1
            
        root = self.xml_tree.getroot()
        new_elem = ET.SubElement(root, 'game')
        
        ET.SubElement(new_elem, 'path').text = f"./{new_key}.zip"
        ET.SubElement(new_elem, 'name').text = new_name
        
        self.games_data[new_key] = new_elem
        self.current_game_element = new_elem
        
        self._refresh_gamelist(reselect_key=new_key)
        self.listbox_selected(new_key, 'game') 

    def del_game(self):
        checked_keys = self.game_list.get_checked_keys()
        
        if not checked_keys:
            messagebox.showwarning("删除警告", "请勾选至少一个要删除的游戏条目。")
            return
            
        if not messagebox.askyesno("确认删除", f"确定要从 XML 中删除选中的 {len(checked_keys)} 个条目吗？(操作不可逆)"):
            return
            
        root = self.xml_tree.getroot()
        
        for key in checked_keys:
            elem = self.games_data.get(key)
            if elem is not None and root is not None:
                root.remove(elem)
                del self.games_data[key]
                if self.current_game_element == elem:
                    self.current_game_element = None
                    
        self._refresh_gamelist()
        self._clear_details()

    def translate_current_game_name(self):
        if not TRANSLATOR_AVAILABLE:
            messagebox.showerror("错误", "请先安装翻译库：pip install deep-translator")
            return
        if not self.current_game_element:
            messagebox.showwarning("警告", "请先选择一个游戏条目。")
            return
            
        original_name = self.game_name_var.get().strip()
        if not original_name:
            messagebox.showwarning("警告", "名称为空，无法翻译。")
            return
            
        try:
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated_name = translator.translate(original_name)
            self._set_var_safe(self.game_name_var, translated_name)
        except Exception as e:
            messagebox.showerror("翻译失败", f"名称翻译失败: {e}")

    def translate_desc(self):
        if not TRANSLATOR_AVAILABLE:
            messagebox.showerror("错误", "请先安装翻译库：pip install deep-translator")
            return
        if not self.current_game_element:
            messagebox.showwarning("警告", "请先选择一个游戏条目。")
            return
            
        original_desc = self.desc_textbox.get("1.0", "end-1c").strip()
        if not original_desc:
            messagebox.showwarning("警告", "描述为空，无法翻译。")
            return
            
        threading.Thread(target=self._start_single_translate_thread, args=(original_desc, 'desc'), daemon=True).start()

    def _start_single_translate_thread(self, text: str, field: str):
        try:
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated_text = translator.translate(text)
            self.after(10, lambda: self._complete_single_translate(translated_text, field))
        except Exception as e:
            self.after(10, lambda: messagebox.showerror("翻译失败", f"描述翻译失败: {e}"))

    def _complete_single_translate(self, translated_text: str, field: str):
        if field == 'desc':
            self.is_updating_ui = True
            self.desc_textbox.delete("1.0", "end")
            self.desc_textbox.insert("1.0", translated_text)
            self.is_updating_ui = False
            self._on_desc_changed(None) 

    def open_one_click_translate_dialog(self):
        if not TRANSLATOR_AVAILABLE:
            messagebox.showerror("错误", "请先安装翻译库：pip install deep-translator")
            return
        if not self.games_data:
            messagebox.showwarning("警告", "列表为空，无法进行批量翻译。")
            return
            
        OneClickTranslateDialog(self, self._start_mass_translate_thread)
        
    def _start_mass_translate_thread(self, field: str):
        target_keys = list(self.games_data.keys())
        total = len(target_keys)
        
        if total == 0:
            return

        self.progress_dialog = CTkProgressDialog(self, f"批量翻译 {field.upper()}...", total)
        
        threading.Thread(target=self._perform_mass_translate, args=(target_keys, field, self.game_list.selected_key), daemon=True).start()
        
    def _perform_mass_translate(self, keys: List[str], field: str, reselect_key: Optional[str]):
        count = 0
        try:
            translator = GoogleTranslator(source='auto', target='zh-CN')
            
            for i, key in enumerate(keys):
                elem = self.games_data.get(key)
                if elem is None:
                    continue
                    
                original_text = elem.findtext(field, '').strip()
                if not original_text:
                    continue
                    
                translated_text = translator.translate(original_text)
                self._update_xml_tag(elem, field, translated_text)
                count += 1
                
                game_name_for_display = elem.findtext('name', key) 
                self.after(10, lambda i=i, name=game_name_for_display: self.progress_dialog.update_progress(i + 1, f"正在翻译 {field}: {name}"))
                time.sleep(0.05) 

            self.after(10, lambda: self._complete_mass_translate(count, field, reselect_key))
            
        except Exception as e:
            self.after(10, lambda: self.progress_dialog.close())
            self.after(10, lambda: messagebox.showerror("翻译失败", f"批量翻译时发生错误: {e}"))
            
    def _complete_mass_translate(self, count: int, field: str, reselect_key: Optional[str]):
                 
        if field == 'name':
             self._refresh_gamelist(reselect_key=reselect_key)
             self.current_game_element = self.games_data.get(reselect_key) if reselect_key else None
             self._clear_details()
             if self.current_game_element:
                 self._load_details_from_selection(self.current_game_element)
        
        elif field == 'desc':
            if self.current_game_element and reselect_key in self.games_data:
                 self._load_details_from_selection(self.games_data[reselect_key])
            
        
        if self.progress_dialog:
             self.progress_dialog.close()
             self.progress_dialog = None

    def _clean_game_name(self, game_name: str) -> str:
        if not game_name:
            return ""
        cleaned_name = re.sub(r'\[.*?\]', '', game_name).strip()
        cleaned_name = re.sub(r'\s*\([^)]*\)$', '', cleaned_name).strip()
        cleaned_name = cleaned_name.replace(' - ', ' ').replace(' / ', ' ')
        return cleaned_name.strip() if cleaned_name else game_name

    def _clear_api_results(self):
        self.api_results_raw_data = None
        self.api_current_games_list.clear()
        self.api_select_var.set("请先刮削...")
        self.api_select_menu.configure(values=["请先刮削..."], state="disabled")

    def _get_platform_name_from_id(self, raw_data: Dict[str, Any], platform_id: str) -> str:
        if not raw_data: return "N/A"
        included_data = raw_data.get('included', [])
        for item in included_data:
             if item.get('type') == 'platforms' and str(item.get('id')) == platform_id:
                return item.get('attributes', {}).get('name', f"ID:{platform_id}")
        return f"ID:{platform_id}"
        
    def _get_names_from_ids(self, raw_data: Dict[str, Any], entity_ids: Any, entity_type: str) -> str:
        if not raw_data or not entity_ids: return ""
        if not isinstance(entity_ids, list): entity_ids = [entity_ids] if entity_ids else []
            
        included_data = raw_data.get('included', []) 
        entity_type_plural = entity_type + 's' 
        entity_map = defaultdict(lambda: 'Unknown') 
        
        for entity in included_data:
            if entity.get('type') == entity_type_plural:
                entity_id = entity.get('id')
                attributes = entity.get('attributes', {})
                name = attributes.get('name')
                if entity_id and name: entity_map[str(entity_id)] = name

        name_list = []
        for entity_id in entity_ids:
            name = entity_map[str(entity_id)]
            if name and name != 'Unknown': name_list.append(name)
        
        clean_list = [str(item).strip() for item in name_list if item is not None and str(item).strip()]
        return ", ".join(clean_list)


    def _handle_scrape_button_click(self):
        if not self.current_game_element:
            messagebox.showwarning("警告", "请先选择一个游戏条目才能开始刮削。")
            return
            
        search_name = self.search_query_var.get().strip()
        if not search_name:
            messagebox.showwarning("警告", "请在 '刮削搜索名称' 字段中输入游戏名称才能开始刮削。")
            return
            
        self.scrape_button.configure(state="disabled", text="刮削中...")
        self.search_query_entry.configure(state="disabled")
        self._clear_api_results()
        
        threading.Thread(target=self._start_scraping_thread, args=(search_name,), daemon=True).start()

    def _start_scraping_thread(self, search_name: str):
        api_response_data = self._perform_real_scraping(search_name)
        self.after(10, lambda: self._complete_scrape_update(api_response_data))

    def _perform_real_scraping(self, search_name: str) -> Dict[str, Any]:
        global requests, API_KEY, API_URL_BY_NAME
        
        if not (requests and API_KEY and API_URL_BY_NAME):
            time.sleep(0.5)
            query_used = search_name
            return {
                "error": f"本地演示数据 (请安装 requests 库)。查询: {query_used}",
                "simulated_data": {
                    "developer": "Demo Dev", "publisher": "Demo Pub", "genre": "Demo/Action/RPG",
                    "players": "1", "releasedate": "2024-01-01", "rating": "0.850000",
                    "overview": f"这是游戏 '{query_used}' 的【本地演示】填充描述。请安装 requests 以启用网络刮削。",
                    "id": "99999", "game_title": f"DEMO GAME: {query_used}"
                }
            }
            
        BASE_FIELDS = "players,releasedate,rating,overview,platform,game_title,developers,publishers,genres" 
        INCLUDE_ENTITIES = "developers,publishers,genres,platforms" 
        API_URL = API_URL_BY_NAME
        params = {
            "apikey": API_KEY, "fields": BASE_FIELDS, "include": INCLUDE_ENTITIES, "name": search_name 
        }
            
        try:
            response = requests.get(API_URL, params=params, timeout=10)
            response.raise_for_status() 
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": f"网络请求失败: {e.__class__.__name__}: {str(e)}"}
        except Exception as e:
            return {"error": f"致命数据处理错误：{e.__class__.__name__}: {str(e)}。"}

    def _complete_scrape_update(self, api_response_data: Dict[str, Any]):
        
        self.scrape_button.configure(state="normal", text="开始刮削")
        self.search_query_entry.configure(state="normal")
        self._clear_api_results()
        
        if api_response_data.get("error"):
            error_msg = f"刮削失败: {api_response_data['error']}"
            if "simulated_data" in api_response_data:
                scraped_data = self._normalize_scraped_data(api_response_data["simulated_data"])
                self._populate_metadata_with_scraped_data(scraped_data)
            else:
                 messagebox.showerror("刮削错误", error_msg)
            return
            
        games_list = api_response_data.get('data', {}).get('games')
        
        if not games_list or len(games_list) == 0:
            messagebox.showwarning("刮削结果", "API 返回成功，但未找到匹配的游戏条目。")
            return

        self.api_results_raw_data = api_response_data
        self.api_current_games_list = games_list
        
        select_options = []
        for game in games_list:
            title = game.get('game_title', 'Unknown Title')
            platform_id = str(game.get('platform', 'N/A')) 
            platform_name = self._get_platform_name_from_id(self.api_results_raw_data, platform_id)
            date = game.get('release_date', 'N/A').split('-')[0] 
            select_options.append(f"[{game.get('id', 'N/A')}] {title} ({platform_name} - {date})")
            
        self.api_select_menu.configure(values=select_options, state="normal")
        self.api_select_var.set(select_options[0]) 
        
        self.after(100, lambda: self._on_api_result_select(select_options[0]))


    def _normalize_scraped_data(self, selected_game_data: Dict[str, Any]) -> Dict[str, Any]:
        
        raw_developers = selected_game_data.get("developers")
        raw_publishers = selected_game_data.get("publishers")
        raw_genres = selected_game_data.get("genres")
        
        date_str = selected_game_data.get("releasedate", selected_game_data.get("release_date", ""))
        
        # 清除 T000000 部分，只保留 YYYYMMDD
        formatted_date = date_str.replace("-", "")[:8]
        if formatted_date and len(formatted_date) == 8:
             formatted_date += "T000000" # 写入 XML 标签时仍需包含 T000000
        else:
             formatted_date = ""

        # UI 显示时不需要 T000000
        ui_date = formatted_date.replace("T000000", "")
             
        desc_value = selected_game_data.get("overview", "")
        raw_players = selected_game_data.get("players")
        players_value = str(raw_players) if raw_players and str(raw_players).lower() not in ('not rated', 'none', '') else ""
            
        scraped_data = {
            "developer": self._get_names_from_ids(self.api_results_raw_data, raw_developers, "developer"),
            "publisher": self._get_names_from_ids(self.api_results_raw_data, raw_publishers, "publisher"),
            "genre": self._get_names_from_ids(self.api_results_raw_data, raw_genres, "genre"),
            "players": players_value, 
            "releasedate": formatted_date, # XML tag value
            "ui_releasedate": ui_date,      # UI display value
            "desc": desc_value
        }
            
        raw_rating = selected_game_data.get('rating')
        scraped_data["rating"] = ""
        if raw_rating is not None and not (isinstance(raw_rating, str) and raw_rating.lower() in ('not rated', 'none', '')):
            try:
                float_rating = float(raw_rating)
                normalized_rating = float_rating
                if float_rating > 10.0: normalized_rating = float_rating / 100.0 
                elif float_rating > 1.0: normalized_rating = float_rating / 10.0 
                normalized_rating = max(0.0, min(1.0, normalized_rating))
                scraped_data["rating"] = f"{normalized_rating:.6f}"
            except ValueError:
                pass
                     
        return scraped_data

    def _on_api_result_select(self, selected_title: str):
        if not self.api_current_games_list or not self.api_results_raw_data: return
            
        match = re.search(r'^\[(\d+|N/A)\]', selected_title)
        selected_id_str = match.group(1) if match else None
        
        selected_game_data = next((game for game in self.api_current_games_list if str(game.get('id')) == selected_id_str), None)
        
        if not selected_game_data:
            messagebox.showerror("填充错误", f"未找到 ID {selected_id_str} 对应的游戏数据。")
            return
            
        scraped_data = self._normalize_scraped_data(selected_game_data)
        self._populate_metadata_with_scraped_data(scraped_data)


    def _populate_metadata_with_scraped_data(self, scraped_data: Dict[str, Any]):
        if self.current_game_element is None: return
            
        self._set_var_safe(self.game_developer_var, scraped_data.get("developer", ""))
        self._set_var_safe(self.game_publisher_var, scraped_data.get("publisher", ""))
        self._set_var_safe(self.game_genre_var, scraped_data.get("genre", ""))
        self._set_var_safe(self.game_players_var, scraped_data.get("players", ""))
        self._set_var_safe(self.game_releasedate_var, scraped_data.get("ui_releasedate", scraped_data.get("releasedate", ""))) # 使用 ui_releasedate
        self._set_var_safe(self.game_rating_var, scraped_data.get("rating", ""))

        desc_text = str(scraped_data.get("desc", "") if scraped_data.get("desc") is not None else "")
        self.is_updating_ui = True
        self.desc_textbox.delete("1.0", "end")
        self.desc_textbox.insert("1.0", desc_text)
        self.is_updating_ui = False
        
        self._on_desc_changed(None) 
        self._do_update() 


    def on_switch_to(self):
        self._initial_load_settings()

    def on_switch_away(self):
        self._clear_details()
        self.game_list.update_list({})
        self.selected_system_name_var.set("(未加载列表)")
        self.xml_tree = None
        self.gamelist_path = None
        self.games_data = {}
        self.is_system_selected = False


register_interface(GamelistEditorPlugin.get_title(), GamelistEditorPlugin.get_order(), GamelistEditorPlugin)