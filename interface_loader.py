from typing import Dict, Type, Any, List, Tuple

# 注册列表：存储 (顺序, 名称, 类) 的元组，以便排序
REGISTERED_INTERFACES: List[Tuple[int, str, Type[Any]]] = []

def register_interface(title: str, order: int, component_class: Type[Any]):
    """注册一个功能界面，供主程序动态加载。"""
    if any(t == title for _, t, _ in REGISTERED_INTERFACES):
        raise ValueError(f"功能名称 '{title}' 已被注册。")
    REGISTERED_INTERFACES.append((order, title, component_class))

def get_available_interfaces() -> Dict[str, Type[Any]]:
    """返回所有已注册的功能界面，按顺序号从小到大排序。"""
    # 按照第一个元素 (order) 排序
    sorted_interfaces = sorted(REGISTERED_INTERFACES, key=lambda x: x[0])
    
    # 转换回 {title: class} 字典，供 WindowShell 使用
    return {title: cls for _, title, cls in sorted_interfaces}