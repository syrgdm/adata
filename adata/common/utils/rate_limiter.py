# -*- coding: utf-8 -*-
"""
@desc: 基于滑动窗口的请求速率限制器
@author: 1nchaos
@time: 2024/1/1
@log: 实现按域名的请求限流，防止触发第三方风控
"""

import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def _find_config_file() -> Optional[str]:
    """
    查找配置文件路径
    
    按以下顺序查找（优先级从高到低）：
    1. 环境变量 ADATA_CONFIG 指定的路径
    2. 当前工作目录下的 config.toml
    3. 项目根目录下的 config.toml
    
    Returns:
        配置文件路径，未找到返回 None
    """
    env_config = os.environ.get('ADATA_CONFIG')
    if env_config and Path(env_config).exists():
        return env_config
    
    cwd_config = Path.cwd() / 'config.toml'
    if cwd_config.exists():
        return str(cwd_config)
    
    package_root = Path(__file__).parent.parent.parent.parent
    root_config = package_root / 'config.toml'
    if root_config.exists():
        return str(root_config)
    
    return None


def _load_config_from_file() -> Dict[str, Any]:
    """
    从配置文件加载限流配置
    
    Returns:
        限流配置字典
    """
    config: Dict[str, Any] = {
        'enabled': True,
        'default_max_requests': 30,
        'default_window_seconds': 60,
        'domain_configs': {}
    }
    
    config_path = _find_config_file()
    if not config_path:
        return config
    
    if tomllib is None:
        import warnings
        warnings.warn(
            "TOML 解析库不可用，请安装 tomli (pip install tomli) 以支持配置文件读取。"
            "将使用默认限流配置。",
            RuntimeWarning
        )
        return config
    
    try:
        with open(config_path, 'rb') as f:
            data = tomllib.load(f)
        
        rate_limit_config = data.get('rate_limit', {})
        
        if 'enabled' in rate_limit_config:
            config['enabled'] = bool(rate_limit_config['enabled'])
        
        if 'default_max_requests' in rate_limit_config:
            config['default_max_requests'] = int(rate_limit_config['default_max_requests'])
        
        if 'default_window_seconds' in rate_limit_config:
            config['default_window_seconds'] = int(rate_limit_config['default_window_seconds'])
        
        domain_configs = rate_limit_config.get('domain_configs', {})
        for domain, domain_config in domain_configs.items():
            max_requests = domain_config.get('max_requests', config['default_max_requests'])
            window_seconds = domain_config.get('window_seconds', config['default_window_seconds'])
            config['domain_configs'][domain.lower()] = (int(max_requests), int(window_seconds))
            
    except Exception as e:
        import warnings
        warnings.warn(
            f"加载限流配置文件失败: {e}，将使用默认配置。",
            RuntimeWarning
        )
    
    return config


class RateLimitConfig:
    """
    限流配置类
    
    支持全局默认配置和按域名差异化配置
    支持从配置文件自动加载配置
    """
    
    _instance_lock = threading.Lock()
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._config_file_loaded = False
        self._default_max_requests = 30
        self._default_window_seconds = 60
        self._domain_configs: Dict[str, tuple] = {}
        self._enabled = True
    
    def load_from_file(self, force: bool = False) -> bool:
        """
        从配置文件加载限流配置
        
        Args:
            force: 是否强制重新加载
            
        Returns:
            是否成功加载配置
        """
        if self._config_file_loaded and not force:
            return True
        
        config = _load_config_from_file()
        
        with self._lock:
            self._enabled = config['enabled']
            self._default_max_requests = config['default_max_requests']
            self._default_window_seconds = config['default_window_seconds']
            self._domain_configs = config['domain_configs'].copy()
            self._config_file_loaded = True
        
        return True
    
    def reload_config(self) -> bool:
        """
        重新加载配置文件
        
        Returns:
            是否成功重新加载
        """
        return self.load_from_file(force=True)
    
    @property
    def enabled(self) -> bool:
        """是否启用限流"""
        return self._enabled
    
    def set_enabled(self, enabled: bool) -> None:
        """
        设置是否启用限流
        
        Args:
            enabled: True 启用，False 禁用
        """
        with self._lock:
            self._enabled = enabled
    
    @property
    def default_max_requests(self) -> int:
        """默认时间窗口内最大请求数"""
        return self._default_max_requests
    
    @property
    def default_window_seconds(self) -> int:
        """默认时间窗口大小（秒）"""
        return self._default_window_seconds
    
    def set_default(self, max_requests: int, window_seconds: int) -> None:
        """
        设置默认限流配置
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        with self._lock:
            self._default_max_requests = max_requests
            self._default_window_seconds = window_seconds
    
    def set_domain_config(self, domain: str, max_requests: int, window_seconds: int) -> None:
        """
        设置指定域名的限流配置
        
        Args:
            domain: 目标域名
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        with self._lock:
            self._domain_configs[domain] = (max_requests, window_seconds)
    
    def get_domain_config(self, domain: str) -> tuple:
        """
        获取指定域名的限流配置
        
        Args:
            domain: 目标域名
            
        Returns:
            (max_requests, window_seconds) 元组
        """
        with self._lock:
            if domain in self._domain_configs:
                return self._domain_configs[domain]
            return (self._default_max_requests, self._default_window_seconds)
    
    def clear_domain_config(self, domain: str) -> None:
        """
        清除指定域名的限流配置，恢复使用默认配置
        
        Args:
            domain: 目标域名
        """
        with self._lock:
            if domain in self._domain_configs:
                del self._domain_configs[domain]
    
    def clear_all_domain_configs(self) -> None:
        """清除所有域名的差异化配置"""
        with self._lock:
            self._domain_configs.clear()


class DomainRateLimiter:
    """
    单个域名的滑动窗口限流器
    
    使用双端队列记录请求时间戳，实现精确的滑动窗口限流
    """
    
    def __init__(self, max_requests: int, window_seconds: int):
        """
        初始化限流器
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = threading.Lock()
    
    def acquire(self) -> float:
        """
        获取请求许可，如果超出限制则返回需要等待的时间
        
        Returns:
            需要等待的时间（秒），0 表示无需等待
        """
        with self._lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            
            while self._timestamps and self._timestamps[0] <= window_start:
                self._timestamps.popleft()
            
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(current_time)
                return 0.0
            
            oldest_timestamp = self._timestamps[0]
            wait_time = oldest_timestamp + self._window_seconds - current_time + 0.001
            return max(0.0, wait_time)
    
    def wait_and_acquire(self) -> None:
        """
        等待并获取请求许可，如果超出限制则自动等待
        
        此方法会阻塞当前线程直到获得请求许可
        """
        wait_time = self.acquire()
        if wait_time > 0:
            time.sleep(wait_time)
            self.acquire()
    
    def update_config(self, max_requests: int, window_seconds: int) -> None:
        """
        更新限流配置
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        with self._lock:
            self._max_requests = max_requests
            self._window_seconds = window_seconds
    
    @property
    def current_count(self) -> int:
        """当前时间窗口内的请求数"""
        with self._lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            while self._timestamps and self._timestamps[0] <= window_start:
                self._timestamps.popleft()
            return len(self._timestamps)


class RateLimiterManager:
    """
    限流器管理器
    
    管理所有域名的限流器实例，提供统一的限流入口
    """
    
    _instance_lock = threading.Lock()
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._limiters: Dict[str, DomainRateLimiter] = {}
        self._lock = threading.Lock()
        self._config = RateLimitConfig()
        self._config.load_from_file()
    
    @staticmethod
    def _extract_domain(url: str) -> str:
        """
        从URL中提取域名
        
        Args:
            url: 完整的URL
            
        Returns:
            域名字符串
        """
        if not url:
            return ''
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if ':' in domain:
            domain = domain.split(':')[0]
        return domain.lower()
    
    def _get_limiter(self, domain: str) -> Optional[DomainRateLimiter]:
        """
        获取或创建指定域名的限流器
        
        Args:
            domain: 目标域名
            
        Returns:
            域名限流器实例
        """
        if not domain:
            return None
        
        with self._lock:
            if domain not in self._limiters:
                max_requests, window_seconds = self._config.get_domain_config(domain)
                self._limiters[domain] = DomainRateLimiter(max_requests, window_seconds)
            else:
                max_requests, window_seconds = self._config.get_domain_config(domain)
                self._limiters[domain].update_config(max_requests, window_seconds)
            return self._limiters[domain]
    
    def before_request(self, url: str) -> None:
        """
        请求前限流检查，如果超出限制则自动等待
        
        Args:
            url: 请求的URL
        """
        if not self._config.enabled:
            return
        
        domain = self._extract_domain(url)
        limiter = self._get_limiter(domain)
        if limiter:
            limiter.wait_and_acquire()
    
    def get_wait_time(self, url: str) -> float:
        """
        获取请求需要等待的时间（不实际等待）
        
        Args:
            url: 请求的URL
            
        Returns:
            需要等待的时间（秒），0 表示无需等待
        """
        if not self._config.enabled:
            return 0.0
        
        domain = self._extract_domain(url)
        limiter = self._get_limiter(domain)
        if limiter:
            return limiter.acquire()
        return 0.0
    
    def get_current_count(self, url: str) -> int:
        """
        获取指定URL当前时间窗口内的请求数
        
        Args:
            url: 请求的URL
            
        Returns:
            当前请求数
        """
        domain = self._extract_domain(url)
        limiter = self._get_limiter(domain)
        if limiter:
            return limiter.current_count
        return 0
    
    def clear_limiter(self, domain: str) -> None:
        """
        清除指定域名的限流器
        
        Args:
            domain: 目标域名
        """
        with self._lock:
            if domain in self._limiters:
                del self._limiters[domain]
    
    def clear_all_limiters(self) -> None:
        """清除所有域名的限流器"""
        with self._lock:
            self._limiters.clear()
    
    @property
    def config(self) -> RateLimitConfig:
        """获取限流配置实例"""
        return self._config


rate_limiter_manager = RateLimiterManager()
rate_limit_config = RateLimitConfig()
