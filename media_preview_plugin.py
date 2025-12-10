import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from pathlib import Path
from typing import Optional, Dict, Any, List
import xml.etree.ElementTree as ET
import sys
import os
import json 
import shutil 

VLC_AVAILABLE = False
try:
    import vlc  # type: ignore[import]
    VLC_AVAILABLE = True
except ImportError:
    pass 

try:
    from PIL import Image, ImageTk 
except ImportError:
    print("FATAL ERROR: 无法找到 Pillow (PIL) 库。请运行 'pip install Pillow' 安装。")
    sys.exit(1)

try:
    from interface_loader import register_interface 
except ImportError:
    def register_interface(*args, **kwargs): pass
    print("警告: 无法导入 interface_loader。插件将以独立模式运行。")


TOOLKIT_CONFIG_FILE = "esde_toolkit_config.json" 

FIXED_PREVIEW_WIDTH = 220
FIXED_PREVIEW_HEIGHT = 220

LIST_BUTTON_HEIGHT = 35
SELECTED_COLOR = "#1F6AA5" 
NORMAL_COLOR = "#2A2A2A"  

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".avi", ".flv", ".wmv"] 


class ToolkitConfigLoader:
    def __init__(self):
        self.config_path = Path(__file__).parent / "config" / TOOLKIT_CONFIG_FILE 
        self.rom_path: Optional[Path] = None 
        self.system_map: Dict[str, Path] = {} 

    def load_config_base_dir(self) -> Optional[str]:
        if not self.config_path.is_file(): return None
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                base_dir_str = config.get('gamelist_base_dir') 
                if base_dir_str and Path(base_dir_str).is_dir(): return base_dir_str
                return None
        except Exception as e:
            return None

    def scan_systems(self, roms_root_path_str: str) -> bool:
        roms_root_path = Path(roms_root_path_str.strip())
        if not roms_root_path.is_dir(): return False 
        self.rom_path = roms_root_path
        self.system_map.clear()
        for system_dir in roms_root_path.iterdir():
            if system_dir.is_dir() and (system_dir / "gamelist.xml").is_file():
                self.system_map[system_dir.name] = system_dir / "gamelist.xml"
        return bool(self.system_map)
    
    def get_system_names(self) -> List[str]:
        return sorted(list(self.system_map.keys()))


MEDIA_TYPES = [
    "miximages", "covers", "screenshots", "titlescreens", 
    "3dboxes", "backcovers", "fanart", "marquees", "physicalmedia", 
] 
# 媒体类型中文名称映射
MEDIA_TYPE_NAMES: Dict[str, str] = {
    "miximages": "混图 (Mix)", 
    "covers": "封面 (Cover)", 
    "screenshots": "截图 (Screenshot)", 
    "titlescreens": "标题画面 (Title)", 
    "3dboxes": "3D 盒 (3D Box)", 
    "backcovers": "封底 (Back Cover)", 
    "fanart": "同人画 (Fanart)", 
    "marquees": "标题艺术图 (Marquee)", 
    "physicalmedia": "实体介质 (Physical)", 
}

MEDIA_EXTENSIONS = {
    "miximages": [".png", ".jpg", ".jpeg"], "covers": [".png", ".jpg", ".jpeg"], 
    "screenshots": [".png", ".jpg", ".jpeg"], "titlescreens": [".png", ".jpg", ".jpeg"], 
    "3dboxes": [".png", ".jpg", ".jpeg"], "backcovers": [".png", ".jpg", ".jpeg"], 
    "fanart": [".png", ".jpg", ".jpeg"], "marquees": [".png", ".jpg", ".jpeg"], 
    "physicalmedia": [".png", ".jpg", ".jpeg"], 
}
IMAGE_TYPES = MEDIA_TYPES


class VlcToplevelWindow:
    def __init__(self, master_tk: tk.Tk, video_path: str, plugin_ref):
        self.plugin_ref = plugin_ref
        self.toplevel = tk.Toplevel(master_tk)
        self.toplevel.title("视频预览 (VLC 嵌入)")
        self.toplevel.geometry("800x600")
        self.toplevel.minsize(400, 300)
        self.toplevel.protocol("WM_DELETE_WINDOW", self.close_window)
        
        self.control_frame = ctk.CTkFrame(self.toplevel, height=40, fg_color=('#3A3A3A', '#2A2A2A'))
        self.control_frame.pack(fill='x', side='top')
        
        self.replace_button = ctk.CTkButton(
            self.control_frame,
            text="更换视频...",
            command=lambda: self.plugin_ref._replace_video_from_toplevel(), 
            fg_color="#E74C3C", 
            hover_color="#C0392B",
            width=120
        )
        self.replace_button.pack(side='left', padx=10, pady=5)
        
        self.video_frame = tk.Frame(self.toplevel, bg='black')
        self.video_frame.pack(fill='both', expand=True)
        
        self.instance = vlc.Instance(['--no-video-title-show', '--quiet'])
        self.player = self.instance.media_player_new()
        
        self.toplevel.update() 
        
        video_handle = self.video_frame.winfo_id() 
        
        if sys.platform.startswith('win'):
            self.player.set_hwnd(video_handle)
        elif sys.platform.startswith('linux'):
            self.player.set_xwindow(video_handle)
        elif sys.platform.startswith('darwin'):
            self.player.set_nsobject(video_handle)
        else:
            plugin_ref._update_status("警告: 当前平台不支持 VLC 嵌入。", "orange")
            self.close_window()
            return
            
        self.play_media(video_path)

    def play_media(self, video_path: str):
        media = self.instance.media_new(video_path)
        self.player.set_media(media)
        self.player.play()
        self.plugin_ref._update_status(f"在 Toplevel 窗口嵌入播放: {Path(video_path).name}", SELECTED_COLOR)

    def close_window(self):
        try:
            self.player.stop()
            self.instance.release()
            self.toplevel.destroy()
        except Exception:
            pass
        finally:
            self.plugin_ref.vlc_player_window = None 


class MediaPreviewPlugin(ctk.CTkFrame):
    
    @staticmethod
    def get_title() -> str:
        return "媒体预览"

    @staticmethod
    def get_order() -> int:
        return 50 

    def __init__(self, master, app_ref, **kwargs):
        super().__init__(master, **kwargs)
        self.app_ref = app_ref 
        self.toolkit_loader = ToolkitConfigLoader() 
        self.game_data: Dict[str, Dict[str, Any]] = {} 
        self.system_select_var = ctk.StringVar(value="等待配置加载系统...")
        self.current_system_name: Optional[str] = None 
        self.current_root_path: Optional[str] = None 
        self.media_photo_references: Dict[str, Optional[ImageTk.PhotoImage]] = {}
        self.media_labels: Dict[str, tk.Label] = {}
        self.preview_frames: Dict[str, ctk.CTkFrame] = {} 
        
        self.list_widgets: Dict[str, ctk.CTkButton] = {} 
        self.selected_game_button: Optional[ctk.CTkButton] = None 
        self.current_game_display_name: Optional[str] = None 
        
        self.current_video_path: Optional[Path] = None 
        self.vlc_player_window: Optional[VlcToplevelWindow] = None 

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1, minsize=100) 
        self.grid_columnconfigure(1, weight=3) 
        
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_frame.grid_rowconfigure(2, weight=1) 
        left_frame.grid_columnconfigure(0, weight=1)
        
        self._create_config_controls(left_frame) 

        ctk.CTkLabel(left_frame, text="游戏列表 (当前系统)", anchor="w").grid(row=1, column=0, sticky="nw", padx=5, pady=(10, 0))
        
        self.list_scroll_frame = ctk.CTkScrollableFrame(
            left_frame, 
            label_text=None,
            fg_color="#242424", 
            border_width=0
        )
        self.list_scroll_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=(0, 5))
        self.list_scroll_frame.columnconfigure(0, weight=1)

        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right_frame.grid_rowconfigure(2, weight=1) 
        right_frame.grid_columnconfigure(0, weight=1)
        
        self._create_preview_controls(right_frame)
        
        media_grid_container = ctk.CTkFrame(right_frame)
        media_grid_container.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        
        media_grid_container.grid_rowconfigure(tuple(range(3)), weight=1) 
        # 修改为 3 列
        media_grid_container.grid_columnconfigure(tuple(range(3)), weight=1) 
        
        self._create_media_grid(media_grid_container)

        self._initial_load()
            
    def _safe_close_vlc_window(self):
        if self.vlc_player_window:
            try:
                self.vlc_player_window.close_window()
            except Exception:
                pass
            
    def _handle_video_button_click(self):
        
        if not self.current_game_display_name:
            self._update_status("请先选择一个游戏。", "orange")
            return

        if self.current_video_path and self.current_video_path.is_file():
            self._play_video()
        else:
            self._upload_video()

    def _play_video(self):

        if not globals().get('VLC_AVAILABLE'):
            messagebox.showerror("视频预览错误", 
                                 "VLC 视频预览功能初始化失败。\n"
                                 "原因：缺少 'python-vlc' 库。如果这不是一个打包后的程序，请运行 'pip install python-vlc'。")
            self._update_status("VLC 库缺失，无法启动预览。", "red")
            return
            
        video_path_str = str(self.current_video_path)
        
        if self.vlc_player_window:
            try:
                self.vlc_player_window.toplevel.lift()
                self.vlc_player_window.toplevel.deiconify()
                self.vlc_player_window.play_media(video_path_str)
            except Exception as e:
                messagebox.showerror("VLC 播放错误", f"VLC 播放器发生内部错误，将尝试重新创建窗口：{e}")
                self._safe_close_vlc_window()
                try:
                    root_tk = self.app_ref.winfo_toplevel()
                    self.vlc_player_window = VlcToplevelWindow(root_tk, video_path_str, self)
                except Exception as e:
                    self._handle_vlc_core_error(e)
            return

        try:
            root_tk = self.app_ref.winfo_toplevel()
            self.vlc_player_window = VlcToplevelWindow(root_tk, video_path_str, self)
        except Exception as e:
            self._handle_vlc_core_error(e)

    def _replace_video_from_toplevel(self):
        
        if not self.current_game_display_name:
            messagebox.showwarning("操作错误", "当前没有选中的游戏。")
            return
            
        selected_game_display = self.current_game_display_name
        game_info = self.game_data.get(selected_game_display)
        
        if not game_info:
            messagebox.showerror("更换失败", "无法获取当前选中游戏的信息。")
            self._update_status("更换视频失败：游戏信息丢失。", "red")
            return
            
        rom_base_name = game_info['rom_base_name']
        system_name = game_info.get('system_name')
        
        self._update_status("正在关闭视频窗口以更换文件...", "orange")
        self._safe_close_vlc_window()
        
        try:
            upload_successful = self._upload_video_file_only(rom_base_name, system_name)
        except Exception as e:
            messagebox.showerror("视频更换失败", f"更换视频文件时发生错误: {e}")
            self._update_status(f"视频更换失败: {e.__class__.__name__}", "red")
            upload_successful = False

        if upload_successful:
            self._update_status("新视频文件已上传，正在重新打开预览...", SELECTED_COLOR)
            self._play_video()
        else:
            self._update_status("视频更换操作已取消或失败。", "orange")
            self.preview_media(rom_base_name=rom_base_name, system_name=system_name)
            
    def _upload_video_file_only(self, rom_base_name: str, system_name: str) -> bool:
        
        if not self.toolkit_loader.rom_path:
            raise ValueError("ROM 根路径未定义。")
            
        video_file_types_dialog = [
            (f"Video files ({'/'.join(VIDEO_EXTENSIONS)})", tuple(VIDEO_EXTENSIONS)),
            ("All files", "*.*")
        ]
        
        new_file_path_str = filedialog.askopenfilename(
            title=f"选择新的视频文件 (支持 {'/'.join(VIDEO_EXTENSIONS)})",
            filetypes=video_file_types_dialog
        )
        
        if not new_file_path_str:
            return False 

        new_file_path = Path(new_file_path_str)
        new_ext = new_file_path.suffix.lower() 
        
        if new_ext not in VIDEO_EXTENSIONS:
            messagebox.showerror("文件格式错误", f"所选文件扩展名 ({new_ext}) 不支持作为视频文件。请选择 {VIDEO_EXTENSIONS} 格式的视频。")
            self._update_status(f"视频文件格式错误: {new_ext}。", "red")
            return False

        esde_data_root = self.toolkit_loader.rom_path.parent
        dest_base_path = esde_data_root / "downloaded_media" / system_name / "videos"
        
        # 使用 rom_base_name (e.g., '01/game') 来构建包含子目录的目标路径
        dest_filename_base = Path(rom_base_name)
        dest_path = dest_base_path / f"{dest_filename_base}{new_ext}"
        
        dest_path.parent.mkdir(parents=True, exist_ok=True) # 确保子目录存在
        
        # 删除所有旧扩展名的视频文件
        for ext in VIDEO_EXTENSIONS:
            old_path = dest_base_path / f"{dest_filename_base}{ext}"
            if old_path.is_file():
                old_path.unlink()
                self._update_status(f"旧视频文件 {old_path.name} 已删除。", "yellow")

        self._update_status("正在复制视频文件，界面将暂时无响应，请稍候...", "blue")
        shutil.copy2(new_file_path, dest_path) 
        
        self.current_video_path = dest_path
        self.preview_media(rom_base_name=rom_base_name, system_name=system_name) 
        
        self._update_status(f"成功上传新视频文件: {dest_path.name}", "#27AE60")
        return True
        
    def _upload_video(self):
        
        selected_game_display = self.current_game_display_name
        game_info = self.game_data.get(selected_game_display)
        
        if not game_info or not self.toolkit_loader.rom_path:
            messagebox.showerror("上传错误", "内部错误：找不到当前选中游戏的数据或 ROM 根路径。")
            return
            
        rom_base_name = game_info['rom_base_name']
        system_name = game_info.get('system_name')

        try:
            self._upload_video_file_only(rom_base_name, system_name)
        except Exception as e:
            messagebox.showerror("视频上传失败", f"上传视频媒体时发生错误: {e}")
            self._update_status(f"视频上传失败: {e.__class__.__name__}", "red")

    def _handle_vlc_core_error(self, error: Exception):
        error_msg = str(error)
        
        if "No such file or directory" in error_msg or "libvlc" in error_msg.lower() or "Failed to load" in error_msg:
            
            messagebox.showerror("VLC 核心组件缺失", 
                                 "无法启动视频播放。\n"
                                 "原因：系统未安装 **VLC 媒体播放器** 或无法找到其核心组件 (libvlc)。\n\n"
                                 "要启用视频预览，请访问官方网站下载并安装 **VLC 媒体播放器**。\n"
                                 "官方网站：https://www.videolan.org/vlc/")
            
            self.vlc_player_window = None 
        else:
             messagebox.showerror("VLC 窗口创建失败", f"无法创建 VLC 播放窗口：{error}")

        self._update_status(f"VLC 启动失败: {error.__class__.__name__}", "red")

    def _create_preview_controls(self, master_frame: ctk.CTkFrame):
        frame = ctk.CTkFrame(master_frame)
        frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 0))
        frame.columnconfigure(0, weight=1) 
        frame.columnconfigure(1, weight=1)
        
        self.status_label = ctk.CTkLabel(frame, text="状态: 准备就绪", text_color="#3498DB")
        self.status_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        
        self.video_button = ctk.CTkButton(
            frame, 
            text="视频预览",
            command=self._handle_video_button_click,
            width=100 
        )
        self.video_button.grid(row=0, column=1, sticky="e", padx=5, pady=5)
        
        ctk.CTkLabel(master_frame, text="当前 ROM 基准名:", anchor="w").grid(
            row=1, column=0, sticky="ew", padx=20, pady=(0, 5))
        self.current_rom_label = ctk.CTkLabel(master_frame, text="未选择游戏", anchor="w", fg_color=("gray90", "gray20"))
        self.current_rom_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 5))

    def _create_config_controls(self, master_frame: ctk.CTkFrame):
        frame = ctk.CTkFrame(master_frame)
        frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="已加载系统:").grid(row=0, column=0, sticky="w", padx=5, pady=0)
        
        self.system_select_menu = ctk.CTkOptionMenu(
            frame, 
            variable=self.system_select_var, 
            values=["等待配置加载系统..."],
            command=self._on_single_select,
            dynamic_resizing=True
        )
        self.system_select_menu.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

    def _create_media_grid(self, master_frame: ctk.CTkFrame):
        
        bg_color = master_frame.cget("fg_color")[1] 
        text_color = "white"
        
        for i, media_type in enumerate(MEDIA_TYPES):
            
            # 修改为 3x3 布局逻辑 (3行3列，共9个元素)
            num_cols = 3
            row = i // num_cols
            col = i % num_cols
            
            slot_frame = ctk.CTkFrame(master_frame, corner_radius=5)
            slot_frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            
            slot_frame.grid_rowconfigure(1, weight=1) 
            slot_frame.grid_columnconfigure(0, weight=1)
            
            self.preview_frames[media_type] = slot_frame 
            
            # 使用中文名称
            display_name = MEDIA_TYPE_NAMES.get(media_type, media_type.replace('_', ' ').title())
            
            ctk.CTkLabel(slot_frame, text=display_name, font=ctk.CTkFont(size=12, weight="bold")).grid(
                row=0, column=0, sticky="ew", pady=(5, 0))
            
            preview_label = tk.Label(slot_frame, 
                                     text="等待选择游戏", 
                                     bg=bg_color, 
                                     fg=text_color,
                                     justify="center",
                                     compound="center",
                                     font=("Arial", 10),
                                     width=FIXED_PREVIEW_WIDTH,
                                     height=FIXED_PREVIEW_HEIGHT) 
                                     
            preview_label.grid(row=1, column=0, sticky="nsew", padx=2, pady=(0, 2))
            
            preview_label.bind("<Double-Button-1>", lambda event, m_type=media_type: self._on_double_click_preview(event, m_type))
            
            self.media_labels[media_type] = preview_label
            self.media_photo_references[media_type] = None

    def _clear_list_and_data(self, clear_listbox: bool = False, reset_text: str = "请选择系统"):
        if clear_listbox: self._clear_list_widgets()
        self.game_data.clear()
        self.current_system_name = None
        self.current_game_display_name = None 
        self.current_video_path = None 
        self._safe_close_vlc_window()
        try:
            self.current_rom_label.configure(text="未选择游戏")
            self.video_button.configure(text="添加视频")
        except tk.TclError: pass
        self._clear_preview(reset_text=reset_text)

    def _clear_preview(self, reset_text: str = "图片预览区域"):
        for key in list(self.media_photo_references.keys()):
            self.media_photo_references[key] = None
        
        self.current_video_path = None 
        self._safe_close_vlc_window()

        try:
            self.video_button.configure(text="添加视频")
        except tk.TclError: pass
        
        for media_type, label in self.media_labels.items():
            try:
                label.configure(image=None) 
                if media_type == MEDIA_TYPES[0]: 
                    label.configure(text=reset_text)
                else: 
                    # 使用中文名称
                    display_name = MEDIA_TYPE_NAMES.get(media_type, media_type.replace('_', ' ').title())
                    label.configure(text=f"无 {display_name}")
            except tk.TclError: pass 

    def preview_media(self, rom_base_name: Optional[str] = None, system_name: Optional[str] = None):
        self._clear_preview(reset_text="正在加载媒体...")
        effective_system_name = system_name if system_name else self.current_system_name
        
        if rom_base_name is None or rom_base_name in ["未选择游戏", ""]:
            self._update_status("请先加载列表并选择一个游戏。", "orange")
            self._clear_preview(reset_text="请先加载列表并选择一个游戏")
            return
            
        try:
            roms_root_path = self.toolkit_loader.rom_path 
            esde_data_root = roms_root_path.parent
        except Exception as e:
            self._update_status(f"路径错误: {e}", "red")
            messagebox.showerror("路径错误", f"无法解析 ES-DE 数据根目录或 ROMs 路径: {e}")
            self._clear_preview(reset_text=f"路径解析失败:\n错误: {e}")
            return

        self._update_status(f"文件扫描中...", "blue")
        success_count = 0
        video_found = False
        
        self.current_video_path = None
        video_base_path = esde_data_root / "downloaded_media" / effective_system_name / "videos"
        # rom_base_name 现在包含子目录，例如 '01/game'
        rom_base_path_for_media = Path(rom_base_name) 

        for ext in VIDEO_EXTENSIONS:
            target_filename = f"{rom_base_path_for_media}{ext}"
            full_path = video_base_path / target_filename # 路径如：.../videos/01/game.mp4
            
            if full_path.is_file():
                self.current_video_path = full_path
                video_found = True
                success_count += 1
                break
        
        try:
            if video_found:
                 self.video_button.configure(text="视频预览")
            else:
                 self.video_button.configure(text="添加视频")
        except tk.TclError:
            pass
        
        for media_type in MEDIA_TYPES:
            label = self.media_labels.get(media_type)
            if not label: continue

            found_file: Optional[Path] = None
            potential_extensions = MEDIA_EXTENSIONS.get(media_type, ['.png', '.jpg'])
            base_path = esde_data_root / "downloaded_media" / effective_system_name / media_type

            for ext in potential_extensions:
                target_filename = f"{rom_base_path_for_media}{ext}"
                full_path = base_path / target_filename # 路径如：.../media_type/01/game.png
                
                if full_path.is_file():
                    found_file = full_path
                    break
            
            if found_file:
                success_count += 1
                self._load_image_preview(found_file, media_type)
            else:
                pass
                
        self._update_status(f"完成加载。找到 {success_count} 个媒体。", "#27AE60")
    
    def _initial_load(self):
        config_path = self.toolkit_loader.load_config_base_dir()
        if config_path:
            self._update_status(f"已从配置文件加载列表源：{config_path}，正在扫描系统...", "blue")
            self._scan_and_populate_systems(config_path)
        else:
            self._update_status("错误：无法从配置文件中找到或加载有效的 'gamelist_base_dir'。", "red")
            self._update_system_menu(None) 
            self._clear_list_and_data(reset_text="配置加载失败，请检查配置文件。")

    def _update_system_menu(self, system_names: Optional[List[str]] = None, current_selection: Optional[str] = None):
        default_value = "未找到任何系统" if not system_names else "等待选择系统"
        if system_names:
            options = system_names
            if current_selection and current_selection in system_names:
                 self.system_select_var.set(current_selection)
            elif system_names:
                 self.system_select_var.set(system_names[0]) 
        else:
            self.system_select_var.set(default_value)
            options = [default_value]
        self.system_select_menu.configure(values=options)

    def _scan_and_populate_systems(self, roms_root_path_to_load: str):
        if self.toolkit_loader.scan_systems(roms_root_path_to_load):
            system_names = self.toolkit_loader.get_system_names()
            self.current_root_path = roms_root_path_to_load
            self._update_system_menu(system_names)
            if system_names:
                self._update_status(f"成功扫描到 {len(system_names)} 个系统，自动加载第一个系统...", "blue")
                self._load_game_list(system_names[0])
            else:
                self._update_status("警告：列表源中未找到任何系统列表。", "orange")
                self._clear_list_and_data()
        else:
            self.current_root_path = None
            self._update_status("错误：找不到有效的系统文件夹。", "red")
            messagebox.showerror("错误", "无法在指定的列表源目录下找到任何包含 gamelist.xml 的系统文件夹。")
            self._update_system_menu(None)
            self._clear_list_and_data()

    def _on_single_select(self, choice: str):
        if choice in self.toolkit_loader.get_system_names():
            self._load_game_list(choice)

    def _select_game_by_name(self, display_name: str):
        clicked_button = self.list_widgets.get(display_name)
        if not clicked_button: return
        
        if self.selected_game_button:
            self.selected_game_button.configure(fg_color=NORMAL_COLOR)
        
        clicked_button.configure(fg_color=SELECTED_COLOR)
        self.selected_game_button = clicked_button
        
        self.current_game_display_name = display_name 

        game_info = self.game_data.get(display_name)
        if game_info:
            rom_base_name = game_info['rom_base_name']
            system_name = game_info['system_name'] 
            
            try:
                self.current_rom_label.configure(text=f"[{system_name.upper()}] {rom_base_name}")
            except tk.TclError: pass
            
            self._update_status(f"游戏: {display_name} 选中，开始加载所有媒体。", SELECTED_COLOR)
            self.preview_media(rom_base_name=rom_base_name, system_name=system_name)

    def _clear_list_widgets(self):
        for widget in self.list_scroll_frame.winfo_children():
            widget.destroy()
        self.list_widgets.clear()
        self.selected_game_button = None

    def _load_game_list(self, system_name: str):
        if system_name == self.current_system_name: return 

        self.current_system_name = system_name
        gamelist_path = self.toolkit_loader.system_map.get(system_name)
        if not gamelist_path:
            self._update_status(f"错误：找不到系统 {system_name} 的 gamelist.xml。", "red")
            return
            
        self._clear_list_and_data(clear_listbox=True) 
        self._clear_preview(reset_text=f"正在加载系统 {system_name} 的游戏...")
        
        try:
            tree = ET.parse(gamelist_path)
            root = tree.getroot()
            total_games = 0
            
            game_names_to_load = []

            for i, game_elem in enumerate(root.findall('game')):
                path_elem = game_elem.find('path')
                name_elem = game_elem.find('name')
                
                if path_elem is not None and path_elem.text:
                    rom_path_text = path_elem.text.strip() # e.g., './01/game.sfc'

                    # --- 关键修改：获取包含子目录的媒体基准名 ---
                    # 1. 移除路径前的 './' 或 '.\'
                    if rom_path_text.startswith('./') or rom_path_text.startswith('.\\'):
                        relative_path_part = Path(rom_path_text[2:])
                    else:
                        relative_path_part = Path(rom_path_text)
                        
                    # 2. 获取不带后缀的完整相对路径作为媒体基准名 (e.g., '01/game')
                    # .as_posix() 确保在 Windows 上路径分隔符正确
                    rom_filename_base = str(relative_path_part.with_suffix('').as_posix()) 
                    # --- 关键修改结束 ---
                    
                    display_name = name_elem.text if name_elem is not None and name_elem.text else Path(rom_path_text).stem
                    
                    game_button = ctk.CTkButton(
                        self.list_scroll_frame,
                        text=display_name,
                        command=lambda name=display_name: self._select_game_by_name(name),
                        height=LIST_BUTTON_HEIGHT,
                        fg_color=NORMAL_COLOR,
                        hover_color=SELECTED_COLOR,
                        corner_radius=6,
                        font=ctk.CTkFont(size=12, weight="bold"),
                        anchor="w" 
                    )
                    game_button.grid(row=i, column=0, sticky="ew", padx=0, pady=(1, 1))
                    
                    self.list_widgets[display_name] = game_button
                    game_names_to_load.append(display_name)
                    
                    self.game_data[display_name] = {
                        'element': game_elem, 
                        'rom_base_name': rom_filename_base, # 包含子目录的基准名
                        'system_name': system_name 
                    }
                    total_games += 1

            self._update_status(f"成功加载系统 {system_name} 的 {total_games} 个游戏。", "#27AE60")
            
            if game_names_to_load:
                self._select_game_by_name(game_names_to_load[0]) 

        except Exception as e:
            self._update_status(f"加载系统 {system_name} 的 XML 失败: {e}", "red")
            messagebox.showerror("错误", f"加载系统 {system_name} 的 XML 失败: {e}")

    def _on_double_click_preview(self, event, media_type: str):
        if not self.current_game_display_name:
            messagebox.showwarning("操作错误", "请先从左侧列表点击选择一个游戏。")
            self._update_status("请先选择一个游戏。", "orange")
            return
            
        try:
            selected_game_display = self.current_game_display_name
            game_info = self.game_data.get(selected_game_display)
            
            if not game_info or not self.toolkit_loader.rom_path:
                raise ValueError("内部错误：找不到当前选中游戏的数据或 ROM 根路径。")
                
            rom_base_name = game_info['rom_base_name'] # 包含子目录 e.g., '01/game'
            system_name = game_info.get('system_name')
            
            if not system_name:
                raise ValueError("内部错误：选中游戏数据中缺失系统名称。")
            
            
            media_chinese_name = MEDIA_TYPE_NAMES.get(media_type, media_type.replace('_', ' ').title())

            warning_title = "媒体文件替换：重要警告"
            warning_message = (
                f"【🛑 危险操作：不可逆】\n\n"
                f"您正在尝试替换当前选中游戏 「{selected_game_display}」 的 「{media_chinese_name}」 媒体文件。\n\n"
                f"***此操作会直接覆盖或新增目标媒体文件夹中的文件，且无法通过本工具撤销（原文件将被永久替换）。）。***\n"
                f"请确认您已对原媒体文件进行备份，并**谨慎操作**。\n"
                f"确定要继续并选择新的媒体文件吗？"
            )
            
            if not messagebox.askyesno(warning_title, warning_message):
                self._update_status("媒体替换操作已取消。", "gray")
                return

            file_types_list = MEDIA_EXTENSIONS.get(media_type, ['.png', '.jpg'])
            file_types_dialog = [
                (f"Image files ({'/'.join(file_types_list)})", tuple(file_types_list)),
                ("All files", "*.*")
            ]
            
            new_file_path_str = filedialog.askopenfilename(
                title=f"选择新的 {media_chinese_name} 图片 (支持 {'/'.join(file_types_list)})",
                filetypes=file_types_dialog
            )
            
            if not new_file_path_str:
                self._update_status("已取消文件选择。", "gray")
                return

            new_file_path = Path(new_file_path_str)
            new_ext = new_file_path.suffix.lower() 
            
            if new_ext not in file_types_list:
                messagebox.showerror("文件格式错误", f"所选文件扩展名 ({new_ext}) 不支持 {media_chinese_name} 类型。请选择 {file_types_list} 格式的图片。")
                self._update_status(f"文件格式错误: {new_ext}。", "red")
                return

            esde_data_root = self.toolkit_loader.rom_path.parent
            dest_base_path = esde_data_root / "downloaded_media" / system_name / media_type
            
            rom_base_path_for_media = Path(rom_base_name) # e.g., '01/game'
            dest_filename = f"{rom_base_path_for_media}{new_ext}"
            dest_path = dest_base_path / dest_filename
            
            dest_path.parent.mkdir(parents=True, exist_ok=True) # 确保子目录存在
            
            # 删除所有旧扩展名的图片文件
            for ext in file_types_list:
                 old_path = dest_base_path / f"{rom_base_path_for_media}{ext}"
                 if old_path.is_file() and old_path != dest_path:
                      old_path.unlink()
                      self._update_status(f"旧图片文件 {old_path.name} 已删除。", "yellow")

            shutil.copy2(new_file_path, dest_path) 
            
            self._load_image_preview(dest_path, media_type)
            self._update_status(f"成功替换/添加 {media_chinese_name} 图片到: {dest_path.name}", "#27AE60")
            
        except Exception as e:
            messagebox.showerror("媒体替换失败", f"替换 {media_type} 媒体时发生错误: {e}")
            self._update_status(f"媒体替换失败: {e.__class__.__name__}", "red")

    def _update_status(self, text: str, color: str = "#3498DB"):
        self.status_label.configure(text=f"状态: {text}", text_color=color)
        self.update_idletasks()

    def _load_image_preview(self, image_path: Path, media_type: str):
        label = self.media_labels.get(media_type)
        if not label: return

        self.media_photo_references[media_type] = None
        
        try:
            from PIL import Image, ImageTk 
            if not image_path.is_file(): raise FileNotFoundError(f"文件不存在: {image_path}")

            img = Image.open(image_path)
            max_width = FIXED_PREVIEW_WIDTH
            max_height = FIXED_PREVIEW_HEIGHT
            img_width, img_height = img.size
            ratio = min(max_width / img_width, max_height / img_height)
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)

            if ratio < 1.0:
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            new_photo_image = ImageTk.PhotoImage(img)
            
            try: label.configure(image=None, text="")
            except tk.TclError: pass 

            self.media_photo_references[media_type] = new_photo_image
            
            label.configure(
                image=self.media_photo_references[media_type], 
                compound="center",
                width=FIXED_PREVIEW_WIDTH,  
                height=FIXED_PREVIEW_HEIGHT 
            ) 
            
        except Exception as e:
            media_chinese_name = MEDIA_TYPE_NAMES.get(media_type, media_type.title())
            self.media_photo_references[media_type] = None
            label.configure(
                image=None, 
                text=f"加载失败\n{e.__class__.__name__}",
                width=FIXED_PREVIEW_WIDTH,
                height=FIXED_PREVIEW_HEIGHT
            )
            self._update_status(f"加载 {media_chinese_name} 失败", "orange")
            
    def on_switch_to(self): 
        self._initial_load()
        pass
    def on_switch_away(self): pass
    def save_config(self): pass
        
register_interface(MediaPreviewPlugin.get_title(), MediaPreviewPlugin.get_order(), MediaPreviewPlugin)