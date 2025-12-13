"""
高级鼠标随机种子生成器
具有华丽的终端显示效果，去除停滞点，并提供丰富的鼠标数据收集功能

安装依赖：
pip install pynput rich colorama
"""

import time
import random
import hashlib
import sys
import math
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from collections import deque
import json

try:
    from pynput import mouse
    from pynput.mouse import Controller as MouseController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("警告: pynput 模块未安装，将使用模拟鼠标位置")
    print("安装命令: pip install pynput")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich.style import Style
    from rich.color import Color
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("提示: rich 模块未安装，将使用简单终端显示")
    print("安装命令: pip install rich")

try:
    from colorama import init, Fore, Back, Style as ColoramaStyle
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False


@dataclass
class MouseDataPoint:
    """鼠标数据点"""
    x: int
    y: int
    timestamp: float
    speed: float  # 相对于上一个点的速度（像素/秒）
    distance: float  # 相对于上一个点的距离
    angle: float  # 相对于上一个点的角度（弧度）


@dataclass
class MouseSeedResult:
    """鼠标种子生成结果"""
    seed: int
    mouse_x: int
    mouse_y: int
    timestamp: float
    hash_digest: str
    method: str
    data_points: int
    total_distance: float
    avg_speed: float
    entropy_score: float


class MouseSeedGenerator:
    """
    高级鼠标随机种子生成器
    
    特性：
    1. 去除停滞点（坐标不变的点）
    2. 实时显示华丽的终端界面
    3. 收集鼠标速度、距离、角度等多维度数据
    4. 计算熵值评估随机性质量
    """
    
    def __init__(self, 
                 min_distance: float = 1.0,  # 最小移动距离，小于此值的点被视为停滞点
                 max_points: int = 1000,     # 保存的最大数据点数
                 sampling_rate: float = 0.01, # 采样率（秒）
                 enable_display: bool = True):
        
        self.min_distance = min_distance
        self.max_points = max_points
        self.sampling_rate = sampling_rate
        
        # 鼠标数据存储
        self.data_points = deque(maxlen=max_points)
        self.raw_points = deque(maxlen=max_points)  # 包括停滞点
        self.last_point = None
        self.last_sample_time = 0
        
        # 统计信息
        self.total_distance = 0.0
        self.total_samples = 0
        self.stagnant_points = 0
        self.start_time = time.time()
        
        # 鼠标控制器
        self.mouse_controller = None
        self.mouse_listener = None
        self.is_listening = False
        
        # 显示设置
        self.enable_display = enable_display and RICH_AVAILABLE
        self.console = Console() if RICH_AVAILABLE else None
        self.display_layout = None
        
        # 初始化鼠标控制器
        self.init_mouse_controller()
    
    def init_mouse_controller(self) -> bool:
        """初始化鼠标控制器"""
        if not PYNPUT_AVAILABLE:
            if self.enable_display:
                self.console.print("[bold red]警告:[/bold red] pynput 不可用，将使用模拟鼠标位置")
            else:
                print("警告: pynput 不可用，将使用模拟鼠标位置")
            return False
        
        try:
            self.mouse_controller = MouseController()
            return True
        except Exception as e:
            if self.enable_display:
                self.console.print(f"[bold red]错误:[/bold red] 初始化鼠标控制器时出错: {e}")
            else:
                print(f"错误: 初始化鼠标控制器时出错: {e}")
            return False
    
    def simulate_mouse_position(self) -> Tuple[int, int]:
        """模拟鼠标位置（用于演示）"""
        t = time.time()
        # 创建复杂的模拟模式
        x = int(800 + 500 * math.sin(t * 0.5) + 200 * math.sin(t * 2.3))
        y = int(400 + 300 * math.cos(t * 0.7) + 150 * math.cos(t * 1.9))
        
        # 添加一些随机噪声
        x += random.randint(-5, 5)
        y += random.randint(-5, 5)
        
        # 确保坐标在合理范围内
        x = max(0, min(1920, x))
        y = max(0, min(1080, y))
        
        return x, y
    
    def get_mouse_position(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        if self.mouse_controller is not None:
            try:
                return self.mouse_controller.position
            except:
                pass
        
        # 使用模拟位置作为后备
        return self.simulate_mouse_position()
    
    def calculate_movement_metrics(self, x1: int, y1: int, x2: int, y2: int, 
                                 time_diff: float) -> Tuple[float, float, float]:
        """计算移动指标：距离、速度、角度"""
        # 计算距离
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx*dx + dy*dy)
        
        # 计算速度（像素/秒）
        speed = distance / time_diff if time_diff > 0 else 0
        
        # 计算角度（弧度）
        if distance > 0:
            angle = math.atan2(dy, dx)
        else:
            angle = 0
        
        return distance, speed, angle
    
    def add_data_point(self, x: int, y: int) -> bool:
        """
        添加鼠标数据点，过滤停滞点
        
        Returns:
            bool: 是否添加了数据点（非停滞点）
        """
        current_time = time.time()
        self.total_samples += 1
        
        # 保存原始点（包括停滞点）
        self.raw_points.append((x, y, current_time))
        
        # 检查是否为停滞点
        if self.last_point is None:
            # 第一个点，总是添加
            distance, speed, angle = 0, 0, 0
            is_stagnant = False
        else:
            # 计算与上一个点的距离
            last_x, last_y, last_time = self.last_point
            time_diff = current_time - last_time
            
            distance, speed, angle = self.calculate_movement_metrics(
                last_x, last_y, x, y, time_diff)
            
            # 检查是否为停滞点
            is_stagnant = distance < self.min_distance or time_diff < 0.001
        
        # 如果不是停滞点，添加到数据点列表
        if not is_stagnant:
            data_point = MouseDataPoint(
                x=x,
                y=y,
                timestamp=current_time,
                speed=speed,
                distance=distance,
                angle=angle
            )
            self.data_points.append(data_point)
            self.total_distance += distance
            
            # 更新上一个点
            self.last_point = (x, y, current_time)
            return True
        else:
            self.stagnant_points += 1
            return False
    
    def start_collecting(self, duration: float = 10.0):
        """开始收集鼠标数据"""
        if self.enable_display:
            self.setup_display()
        
        self.start_time = time.time()
        self.is_listening = True
        
        # 定义鼠标移动回调
        def on_move(x, y):
            current_time = time.time()
            
            # 限制采样率
            if current_time - self.last_sample_time >= self.sampling_rate:
                self.add_data_point(x, y)
                self.last_sample_time = current_time
            
            # 如果启用了显示，则更新
            if self.enable_display:
                self.update_display()
        
        # 启动鼠标监听器
        if PYNPUT_AVAILABLE:
            self.mouse_listener = mouse.Listener(on_move=on_move)
            self.mouse_listener.start()
        
        # 如果没有pynput，使用模拟模式
        else:
            import threading
            def simulate_mouse_movement():
                while self.is_listening and (time.time() - self.start_time < duration):
                    x, y = self.simulate_mouse_position()
                    on_move(x, y)
                    time.sleep(self.sampling_rate)
            
            sim_thread = threading.Thread(target=simulate_mouse_movement)
            sim_thread.start()
        
        # 等待指定时间或用户中断
        try:
            if self.enable_display:
                with Live(self.display_layout, refresh_per_second=10, screen=True):
                    while time.time() - self.start_time < duration and self.is_listening:
                        time.sleep(0.1)
            else:
                # 简单显示模式
                print("开始收集鼠标数据...")
                print("移动鼠标以生成随机数据 (按Ctrl+C停止)...")
                print("-" * 50)
                
                start_time = time.time()
                while time.time() - start_time < duration and self.is_listening:
                    time.sleep(0.1)
                    # 简单更新显示
                    if self.data_points and time.time() - self.last_display_time > 0.5:
                        self.simple_display()
                        self.last_display_time = time.time()
        
        except KeyboardInterrupt:
            print("\n用户中断数据收集")
        finally:
            self.stop_collecting()
    
    def stop_collecting(self):
        """停止收集鼠标数据"""
        self.is_listening = False
        
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
    
    def calculate_entropy(self) -> float:
        """计算鼠标移动的熵值（衡量随机性）"""
        if len(self.data_points) < 10:
            return 0.0
        
        # 基于角度分布的熵
        angle_bins = 16
        angle_counts = [0] * angle_bins
        
        for point in self.data_points:
            if point.distance > 0:
                # 将角度映射到 [0, 2π) 然后分箱
                normalized_angle = (point.angle + math.pi) % (2 * math.pi)
                bin_idx = int(normalized_angle / (2 * math.pi) * angle_bins)
                bin_idx = min(bin_idx, angle_bins - 1)
                angle_counts[bin_idx] += 1
        
        # 计算熵
        total = sum(angle_counts)
        if total == 0:
            return 0.0
        
        entropy = 0.0
        for count in angle_counts:
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        # 归一化到 [0, 1]
        max_entropy = math.log2(angle_bins)
        return entropy / max_entropy
    
    def generate_seed_from_movement(self) -> MouseSeedResult:
        """从鼠标移动数据生成随机种子"""
        if not self.data_points:
            # 如果没有收集到数据，使用简单方法
            return self.generate_simple_seed()
        
        # 计算统计信息
        if self.data_points:
            avg_speed = sum(p.speed for p in self.data_points) / len(self.data_points)
            entropy_score = self.calculate_entropy()
        else:
            avg_speed = 0.0
            entropy_score = 0.0
        
        # 使用鼠标数据生成种子
        seed_data = ""
        for point in list(self.data_points)[-100:]:  # 使用最近的100个点
            seed_data += f"{point.x},{point.y},{point.speed:.2f},{point.angle:.4f};"
        
        # 添加时间戳
        current_time = time.time()
        seed_data += str(current_time)
        
        # 生成哈希
        hash_digest = hashlib.sha256(seed_data.encode()).hexdigest()
        
        # 将哈希转换为整数种子
        seed_int = int(hash_digest[:16], 16) % (2**31)
        
        # 获取最后一个点
        last_point = self.data_points[-1] if self.data_points else None
        
        return MouseSeedResult(
            seed=seed_int,
            mouse_x=last_point.x if last_point else 0,
            mouse_y=last_point.y if last_point else 0,
            timestamp=current_time,
            hash_digest=hash_digest,
            method="mouse_movement_entropy",
            data_points=len(self.data_points),
            total_distance=self.total_distance,
            avg_speed=avg_speed,
            entropy_score=entropy_score
        )
    
    def generate_simple_seed(self) -> MouseSeedResult:
        """生成简单种子（用于向后兼容）"""
        x, y = self.get_mouse_position()
        current_time = time.time()
        
        # 将鼠标位置和时间戳结合生成种子
        seed_value = int((x * 10000 + y) * current_time) % (2**31)
        
        # 创建哈希摘要
        hash_input = f"{x},{y},{current_time}"
        hash_digest = hashlib.md5(hash_input.encode()).hexdigest()
        
        return MouseSeedResult(
            seed=seed_value,
            mouse_x=x,
            mouse_y=y,
            timestamp=current_time,
            hash_digest=hash_digest,
            method="simple_mouse_position",
            data_points=len(self.data_points),
            total_distance=self.total_distance,
            avg_speed=0.0,
            entropy_score=0.0
        )
    
    def setup_display(self):
        """设置华丽的终端显示界面"""
        if not self.enable_display:
            return
        
        # 创建布局
        self.display_layout = Layout()
        
        # 分割窗口
        self.display_layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=2),
            Layout(name="stats", size=12),
            Layout(name="footer", size=3)
        )
        
        # 分割主区域
        self.display_layout["main"].split_row(
            Layout(name="data", ratio=2),
            Layout(name="visual", ratio=1)
        )
    
    def update_display(self):
        """更新显示界面"""
        if not self.enable_display or not self.display_layout:
            return
        
        # 头部 - 标题和状态
        header_text = Text("🐭 高级鼠标随机种子生成器 🐭", style="bold cyan")
        header_text.append("\n")
        header_text.append("移动鼠标收集随机数据 | ", style="yellow")
        header_text.append("按 Ctrl+C 停止", style="bold red")
        
        self.display_layout["header"].update(
            Panel(header_text, style="bold white", border_style="cyan")
        )
        
        # 主区域 - 数据
        data_table = Table(show_header=True, box=box.ROUNDED)
        data_table.add_column("指标", style="cyan")
        data_table.add_column("值", style="green")
        data_table.add_column("状态", style="yellow")
        
        # 添加数据行
        elapsed_time = time.time() - self.start_time
        data_table.add_row("收集时间", f"{elapsed_time:.1f} 秒", "⏱️")
        data_table.add_row("有效数据点", str(len(self.data_points)), "✅" if len(self.data_points) > 10 else "⚠️")
        data_table.add_row("总采样点", str(self.total_samples), "📊")
        data_table.add_row("停滞点过滤", str(self.stagnant_points), "🗑️")
        data_table.add_row("总移动距离", f"{self.total_distance:.1f} 像素", "📏")
        
        if self.data_points:
            recent_speed = self.data_points[-1].speed if len(self.data_points) > 0 else 0
            data_table.add_row("当前速度", f"{recent_speed:.1f} px/s", "🚀" if recent_speed > 50 else "🐢")
        
        entropy = self.calculate_entropy()
        entropy_status = "🌟" if entropy > 0.7 else "✅" if entropy > 0.4 else "⚠️"
        data_table.add_row("随机性熵值", f"{entropy:.3f}", entropy_status)
        
        self.display_layout["data"].update(
            Panel(data_table, title="数据统计", border_style="green")
        )
        
        # 主区域 - 可视化
        if self.data_points and len(self.data_points) > 1:
            visual_text = self.create_visualization()
            self.display_layout["visual"].update(
                Panel(visual_text, title="移动模式", border_style="magenta")
            )
        else:
            self.display_layout["visual"].update(
                Panel(Text("等待足够的数据...", style="dim"), 
                      title="移动模式", border_style="magenta")
            )
        
        # 统计区域 - 详细统计
        stats_text = self.create_detailed_stats()
        self.display_layout["stats"].update(
            Panel(stats_text, title="详细统计", border_style="yellow")
        )
        
        # 底部 - 种子信息
        if len(self.data_points) >= 10:
            seed_result = self.generate_seed_from_movement()
            footer_text = Text()
            footer_text.append("当前种子值: ", style="bold")
            footer_text.append(f"{seed_result.seed}", style="bold green")
            footer_text.append(" | 哈希: ", style="bold")
            footer_text.append(f"{seed_result.hash_digest[:16]}...", style="dim")
            footer_text.append(" | 方法: ", style="bold")
            footer_text.append(seed_result.method, style="cyan")
        else:
            footer_text = Text("收集更多数据以生成高质量种子...", style="italic yellow")
        
        self.display_layout["footer"].update(
            Panel(footer_text, border_style="blue")
        )
    
    def create_visualization(self) -> Text:
        """创建鼠标移动可视化"""
        if len(self.data_points) < 2:
            return Text("数据不足")
        
        # 获取最近的点用于可视化
        recent_points = list(self.data_points)[-20:]  # 最近20个点
        
        # 创建简单的ASCII可视化
        rows = 10
        cols = 30
        
        # 初始化网格
        grid = [[' ' for _ in range(cols)] for _ in range(rows)]
        
        # 找到坐标范围
        if recent_points:
            xs = [p.x for p in recent_points]
            ys = [p.y for p in recent_points]
            
            if max(xs) - min(xs) > 0 and max(ys) - min(ys) > 0:
                # 将坐标映射到网格
                for i, point in enumerate(recent_points):
                    col = int((point.x - min(xs)) / (max(xs) - min(xs)) * (cols - 1))
                    row = int((point.y - min(ys)) / (max(ys) - min(ys)) * (rows - 1))
                    
                    # 确保在边界内
                    col = max(0, min(cols-1, col))
                    row = max(0, min(rows-1, row))
                    
                    # 设置字符（根据点的位置）
                    if i == len(recent_points) - 1:
                        grid[row][col] = '●'  # 当前点
                    elif i == 0:
                        grid[row][col] = '○'  # 起点
                    else:
                        grid[row][col] = '·'  # 路径点
        
        # 创建文本
        text = Text()
        for row in grid:
            line = ''.join(row)
            text.append(line + '\n', style="green")
        
        return text
    
    def create_detailed_stats(self) -> Text:
        """创建详细统计信息"""
        text = Text()
        
        if len(self.data_points) < 2:
            text.append("等待更多数据...", style="dim")
            return text
        
        # 计算统计数据
        speeds = [p.speed for p in self.data_points if p.speed > 0]
        distances = [p.distance for p in self.data_points if p.distance > 0]
        
        if speeds:
            avg_speed = sum(speeds) / len(speeds)
            max_speed = max(speeds)
            min_speed = min(speeds)
            
            text.append("速度统计:\n", style="bold cyan")
            text.append(f"  平均: {avg_speed:.1f} px/s\n")
            text.append(f"  最大: {max_speed:.1f} px/s\n")
            text.append(f"  最小: {min_speed:.1f} px/s\n\n")
        
        if distances:
            avg_distance = sum(distances) / len(distances)
            total_distance = sum(distances)
            
            text.append("距离统计:\n", style="bold cyan")
            text.append(f"  平均移动: {avg_distance:.1f} 像素\n")
            text.append(f"  总移动: {total_distance:.1f} 像素\n")
            
            # 估计实际移动距离（考虑停滞点）
            estimated_actual = total_distance * (len(self.data_points) / self.total_samples)
            text.append(f"  估计实际: {estimated_actual:.1f} 像素\n\n")
        
        # 方向分布
        if len(self.data_points) > 10:
            angles = [p.angle for p in self.data_points if p.distance > 0]
            if angles:
                # 转换为方向（0-7，代表8个方向）
                directions = [0] * 8
                for angle in angles:
                    # 将角度从[-π, π]转换到[0, 2π]
                    normalized = (angle + math.pi) % (2 * math.pi)
                    dir_idx = int(normalized / (2 * math.pi) * 8) % 8
                    directions[dir_idx] += 1
                
                text.append("方向分布:\n", style="bold cyan")
                dir_names = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
                for i, (name, count) in enumerate(zip(dir_names, directions)):
                    percentage = count / len(angles) * 100
                    bar = "█" * int(percentage / 5)
                    text.append(f"  {name}: {bar} {percentage:.1f}%\n")
        
        return text
    
    def simple_display(self):
        """简单终端显示（当rich不可用时）"""
        if COLORAMA_AVAILABLE:
            # 使用colorama的彩色显示
            print(f"\033[2J\033[H", end="")  # 清屏
            print(f"{Fore.CYAN}{'='*60}{Fore.RESET}")
            print(f"{Fore.YELLOW}鼠标随机种子生成器{Fore.RESET}")
            print(f"{Fore.CYAN}{'='*60}{Fore.RESET}")
            
            print(f"\n{Fore.GREEN}数据收集:{Fore.RESET}")
            print(f"  有效点: {len(self.data_points)}")
            print(f"  总采样: {self.total_samples}")
            print(f"  停滞点: {self.stagnant_points}")
            print(f"  总距离: {self.total_distance:.1f} 像素")
            
            if self.data_points:
                print(f"  当前速度: {self.data_points[-1].speed:.1f} px/s")
                entropy = self.calculate_entropy()
                print(f"  熵值: {entropy:.3f}")
            
            print(f"\n{Fore.GREEN}操作:{Fore.RESET}")
            print(f"  移动鼠标以生成数据")
            print(f"  按 {Fore.RED}Ctrl+C{Fore.RESET} 停止收集")
            
            if len(self.data_points) >= 10:
                seed_result = self.generate_seed_from_movement()
                print(f"\n{Fore.GREEN}当前种子:{Fore.RESET}")
                print(f"  值: {Fore.CYAN}{seed_result.seed}{Fore.RESET}")
                print(f"  哈希: {seed_result.hash_digest[:16]}...")
        else:
            # 简单文本显示
            print(f"\n数据点: {len(self.data_points)} | "
                  f"总采样: {self.total_samples} | "
                  f"停滞点: {self.stagnant_points} | "
                  f"距离: {self.total_distance:.1f}px", end="")
    
    def get_seed(self, method: str = "movement") -> MouseSeedResult:
        """
        获取随机种子
        
        Args:
            method: 生成方法 ("movement" 或 "simple")
        
        Returns:
            MouseSeedResult: 种子结果
        """
        if method == "movement" and self.data_points:
            return self.generate_seed_from_movement()
        else:
            return self.generate_simple_seed()


# 全局函数接口（供其他程序调用）
def collect_mouse_data_and_generate_seed(
    duration: float = 5.0,
    min_distance: float = 1.0,
    enable_display: bool = True
) -> dict:
    """
    收集鼠标数据并生成种子（主要接口）
    
    Args:
        duration: 收集时间（秒）
        min_distance: 最小移动距离（小于此值视为停滞点）
        enable_display: 是否启用华丽显示
    
    Returns:
        dict: 包含种子和统计信息的字典
    """
    generator = MouseSeedGenerator(
        min_distance=min_distance,
        enable_display=enable_display
    )
    
    print(f"开始收集鼠标数据，持续 {duration} 秒...")
    generator.start_collecting(duration=duration)
    
    # 生成种子
    result = generator.get_seed("movement")
    
    # 转换为字典返回
    return {
        "seed": result.seed,
        "mouse_x": result.mouse_x,
        "mouse_y": result.mouse_y,
        "timestamp": result.timestamp,
        "hash": result.hash_digest,
        "method": result.method,
        "data_points": result.data_points,
        "total_distance": result.total_distance,
        "avg_speed": result.avg_speed,
        "entropy_score": result.entropy_score,
        "collection_time": duration,
        "stagnant_points_removed": generator.stagnant_points
    }


def quick_seed() -> int:
    """
    快速生成种子（简单接口）
    
    Returns:
        int: 随机种子
    """
    generator = MouseSeedGenerator(enable_display=False)
    generator.start_collecting(duration=1.0)
    result = generator.get_seed("movement")
    return result.seed


# 演示代码
if __name__ == "__main__":
    print("=== 高级鼠标随机种子生成器 ===\n")
    
    # 检查依赖
    if not PYNPUT_AVAILABLE:
        print("注意: 未检测到真实鼠标，将使用模拟模式")
        print("      安装 pynput 以使用真实鼠标: pip install pynput\n")
    
    if not RICH_AVAILABLE:
        print("注意: 未安装 rich 库，将使用简单显示模式")
        print("      安装 rich 以获得最佳体验: pip install rich\n")
    
    # 演示选项
    print("选择模式:")
    print("  1. 快速生成种子 (1秒)")
    print("  2. 标准收集 (5秒)")
    print("  3. 详细收集 (10秒)")
    print("  4. 自定义收集")
    print("  5. 退出")
    
    choice = input("\n请输入选择 (1-5): ").strip()
    
    if choice == "1":
        # 快速生成
        seed = quick_seed()
        print(f"\n生成的种子: {seed}")
        
    elif choice == "2":
        # 标准收集
        result = collect_mouse_data_and_generate_seed(duration=5.0)
        print(f"\n收集完成!")
        print(f"种子: {result['seed']}")
        print(f"数据点: {result['data_points']}")
        print(f"熵值: {result['entropy_score']:.3f}")
        
    elif choice == "3":
        # 详细收集
        result = collect_mouse_data_and_generate_seed(duration=10.0)
        print(f"\n收集完成!")
        print(f"种子: {result['seed']}")
        print(f"数据点: {result['data_points']}")
        print(f"总移动距离: {result['total_distance']:.1f} 像素")
        print(f"平均速度: {result['avg_speed']:.1f} px/s")
        print(f"熵值: {result['entropy_score']:.3f}")
        
    elif choice == "4":
        # 自定义收集
        try:
            duration = float(input("收集时长 (秒): "))
            min_dist = float(input("最小移动距离 (像素): "))
            
            result = collect_mouse_data_and_generate_seed(
                duration=duration,
                min_distance=min_dist
            )
            
            print(f"\n收集完成!")
            print(json.dumps(result, indent=2, default=str))
            
        except ValueError:
            print("输入无效!")
            
    elif choice == "5":
        print("再见!")
        
    else:
        print("无效选择!")