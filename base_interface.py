import customtkinter as ctk
from abc import ABC, abstractmethod
from typing import Any

class BaseInterface(ctk.CTkFrame, ABC):
    """所有功能界面必须继承的抽象基类。"""
    
    def __init__(self, master: Any, app_ref: Any, **kwargs):
        super().__init__(master, **kwargs)
        self.app_ref = app_ref 
        
    @staticmethod
    @abstractmethod
    def get_title() -> str:
        """返回该界面在导航栏上显示的中文名称。"""
        pass

    @staticmethod
    @abstractmethod
    def get_order() -> int:
        """返回该界面在导航栏上的显示顺序（数字越小越靠前）。"""
        pass

    @abstractmethod
    def create_ui(self):
        """实际绘制 UI 控件的方法。"""
        pass
        
    def on_switch_to(self):
        """(可选) 当主程序切换到此界面时执行的操作。"""
        pass
        
    def on_switch_away(self):
        """(可选) 当主程序从当前界面切换走时执行的清理操作。"""
        pass
        
    def save_config(self):
        """(可选) 允许主程序调用插件的保存方法。"""
        pass