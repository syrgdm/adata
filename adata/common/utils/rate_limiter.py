# -*- coding: utf-8 -*-
"""
@desc: 请求限流器 - 按域名实现请求速率限制，防止触发第三方风控
@author: 1nchaos
@time: 2026/4/15
@log: 实现按域名的请求限流，防止触发第三方风控
"""

import functools
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Any
from urllib.parse import urlparse


@dataclass
class RateLimitConfig:
    """
    限流配置类
    
    Attributes:
        max_requests: 时间窗口内最大请求次数，默认30次
        time_window: 时间窗口大小（秒），默认60秒
        wait_timeout: 等待超时时间（秒），默认None表示无限等待
    """
    max_requests: int = 30
    time_window: int = 60
    wait_timeout: Optional[float] = None


class SlidingWindowRateLimiter:
    """
    基于滑动窗口算法的域名级请求限流器
    
    特点：
    1. 按域名独立计数，不同域名互不影响
    2. 线程安全，支持高并发场景
    3. 基于内存实现，轻量级无外部依赖
    4. 支持等待队列，超出限流时自动排队等待
    
    Usage:
        limiter = SlidingWindowRateLimiter()
        
        # 方式1：直接检查并等待
        limiter.acquire("https://api.example.com/data")
        
        # 方式2：使用装饰器
        @limiter.rate_limit()
        def fetch_data(url):
            return requests.get(url)
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式，确保全局只有一个限流器实例"""
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        """
        初始化限流器
        
        Args:
            default_config: 默认限流配置，如不传入则使用默认值
        """
        # 避免重复初始化
        if self._initialized:
            return
            
        self._default_config = default_config or RateLimitConfig()
        
        # 域名 -> 请求时间队列 的映射
        self._domain_windows: Dict[str, deque] = {}
        
        # 域名 -> 限流配置 的映射
        self._domain_configs: Dict[str, RateLimitConfig] = {}
        
        # 每个域名对应的锁，保证线程安全
        self._domain_locks: Dict[str, threading.Lock] = {}
        
        # 全局锁，用于操作域名映射表
        self._global_lock = threading.Lock()
        
        self._initialized = True
    
    def _get_domain(self, url: str) -> str:
        """
        从URL中提取域名
        
        Args:
            url: 请求URL
            
        Returns:
            域名（如：api.example.com）
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # 如果netloc为空，返回原始字符串
            return domain if domain else url.lower()
        except Exception:
            # URL解析失败时，返回原始字符串作为域名标识
            return url.lower()
    
    def _get_domain_lock(self, domain: str) -> threading.Lock:
        """
        获取指定域名的锁，如果不存在则创建
        
        Args:
            domain: 域名
            
        Returns:
            该域名对应的线程锁
        """
        if domain not in self._domain_locks:
            with self._global_lock:
                if domain not in self._domain_locks:
                    self._domain_locks[domain] = threading.Lock()
        return self._domain_locks[domain]
    
    def _get_domain_window(self, domain: str) -> deque:
        """
        获取指定域名的请求时间窗口，如果不存在则创建
        
        Args:
            domain: 域名
            
        Returns:
            该域名的请求时间队列
        """
        if domain not in self._domain_windows:
            with self._global_lock:
                if domain not in self._domain_windows:
                    self._domain_windows[domain] = deque()
        return self._domain_windows[domain]
    
    def _get_domain_config(self, domain: str) -> RateLimitConfig:
        """
        获取指定域名的限流配置
        
        Args:
            domain: 域名
            
        Returns:
            该域名的限流配置
        """
        return self._domain_configs.get(domain, self._default_config)
    
    def set_domain_config(self, domain: str, config: RateLimitConfig) -> None:
        """
        为指定域名设置限流配置
        
        Args:
            domain: 域名
            config: 限流配置
        """
        with self._global_lock:
            self._domain_configs[domain.lower()] = config
    
    def _clean_expired_requests(self, window: deque, current_time: float, time_window: int) -> None:
        """
        清理时间窗口中已过期的请求记录
        
        Args:
            window: 请求时间队列
            current_time: 当前时间戳
            time_window: 时间窗口大小（秒）
        """
        cutoff_time = current_time - time_window
        # 从队列左侧移除过期的时间戳
        while window and window[0] < cutoff_time:
            window.popleft()
    
    def acquire(self, url: str, blocking: bool = True) -> bool:
        """
        尝试获取请求许可
        
        Args:
            url: 请求的URL
            blocking: 是否阻塞等待，True表示等待直到获取许可，False表示立即返回
        
        Returns:
            True表示获取许可成功，False表示被限流（仅在non-blocking模式下可能返回）
            
        Raises:
            TimeoutError: 当等待超时且配置了wait_timeout时抛出
        """
        domain = self._get_domain(url)
        config = self._get_domain_config(domain)
        window = self._get_domain_window(domain)
        domain_lock = self._get_domain_lock(domain)
        
        start_time = time.time()
        
        while True:
            with domain_lock:
                current_time = time.time()
                
                # 清理过期请求
                self._clean_expired_requests(window, current_time, config.time_window)
                
                # 检查是否还有请求额度
                if len(window) < config.max_requests:
                    # 记录当前请求时间
                    window.append(current_time)
                    return True
            
            # 超出限流限制
            if not blocking:
                return False
            
            # 检查超时
            if config.wait_timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= config.wait_timeout:
                    raise TimeoutError(
                        f"获取请求许可超时: 域名 {domain} 限流阈值 "
                        f"{config.max_requests}次/{config.time_window}秒"
                    )
            
            # 短暂等待后重试
            time.sleep(0.1)
    
    def try_acquire(self, url: str) -> bool:
        """
        非阻塞方式尝试获取请求许可
        
        Args:
            url: 请求的URL
            
        Returns:
            True表示获取许可成功，False表示被限流
        """
        return self.acquire(url, blocking=False)
    
    def get_current_count(self, url: str) -> int:
        """
        获取指定URL对应域名的当前请求计数
        
        Args:
            url: 请求的URL
            
        Returns:
            当前时间窗口内的请求次数
        """
        domain = self._get_domain(url)
        config = self._get_domain_config(domain)
        window = self._get_domain_window(domain)
        domain_lock = self._get_domain_lock(domain)
        
        with domain_lock:
            current_time = time.time()
            self._clean_expired_requests(window, current_time, config.time_window)
            return len(window)
    
    def get_remaining_quota(self, url: str) -> int:
        """
        获取指定URL对应域名的剩余请求额度
        
        Args:
            url: 请求的URL
            
        Returns:
            当前时间窗口内剩余的请求次数
        """
        domain = self._get_domain(url)
        config = self._get_domain_config(domain)
        current_count = self.get_current_count(url)
        return max(0, config.max_requests - current_count)
    
    def rate_limit(
        self, 
        url_extractor: Optional[Callable] = None,
        config: Optional[RateLimitConfig] = None
    ) -> Callable:
        """
        装饰器：为函数添加限流功能
        
        Args:
            url_extractor: URL提取函数，用于从被装饰函数的参数中提取URL
                          如果为None，则默认取第一个位置参数
            config: 该函数专用的限流配置，覆盖默认配置
            
        Returns:
            装饰器函数
            
        Usage:
            # 方式1：自动提取第一个参数作为URL
            @limiter.rate_limit()
            def fetch_data(url, **kwargs):
                return requests.get(url, **kwargs)
            
            # 方式2：自定义URL提取
            @limiter.rate_limit(url_extractor=lambda **kwargs: kwargs.get('api_url'))
            def fetch_data(api_url=None, **kwargs):
                return requests.get(api_url, **kwargs)
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # 提取URL
                if url_extractor:
                    url = url_extractor(*args, **kwargs)
                elif args:
                    url = str(args[0])
                else:
                    url = kwargs.get('url', '')
                
                if url:
                    # 如果提供了专用配置，临时设置
                    if config:
                        domain = self._get_domain(url)
                        original_config = self._domain_configs.get(domain)
                        self.set_domain_config(domain, config)
                    
                    try:
                        # 获取限流许可
                        self.acquire(url)
                    finally:
                        # 恢复原始配置
                        if config and original_config:
                            self.set_domain_config(domain, original_config)
                
                # 执行原函数
                return func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    def reset(self, url: Optional[str] = None) -> None:
        """
        重置限流器状态
        
        Args:
            url: 如果提供，则只重置该URL对应域名的状态；
                 如果不提供，则重置所有域名的状态
        """
        if url:
            domain = self._get_domain(url)
            with self._get_domain_lock(domain):
                if domain in self._domain_windows:
                    self._domain_windows[domain].clear()
        else:
            with self._global_lock:
                for window in self._domain_windows.values():
                    window.clear()


# 全局限流器实例
rate_limiter = SlidingWindowRateLimiter()


def rate_limit_by_domain(
    max_requests: int = 30,
    time_window: int = 60,
    wait_timeout: Optional[float] = None,
    url_extractor: Optional[Callable] = None
) -> Callable:
    """
    便捷装饰器：按域名限流
    
    这是SlidingWindowRateLimiter.rate_limit的便捷包装，使用全局限流器实例
    
    Args:
        max_requests: 时间窗口内最大请求次数
        time_window: 时间窗口大小（秒）
        wait_timeout: 等待超时时间（秒）
        url_extractor: URL提取函数
        
    Returns:
        装饰器函数
        
    Usage:
        from adata.common.utils.rate_limiter import rate_limit_by_domain
        
        @rate_limit_by_domain(max_requests=30, time_window=60)
        def fetch_stock_data(url):
            return requests.get(url).json()
    """
    config = RateLimitConfig(
        max_requests=max_requests,
        time_window=time_window,
        wait_timeout=wait_timeout
    )
    return rate_limiter.rate_limit(url_extractor=url_extractor, config=config)


def configure_domain_limit(domain: str, max_requests: int, time_window: int) -> None:
    """
    为指定域名配置限流参数
    
    Args:
        domain: 域名（如：push2.eastmoney.com）
        max_requests: 时间窗口内最大请求次数
        time_window: 时间窗口大小（秒）
        
    Usage:
        from adata.common.utils.rate_limiter import configure_domain_limit
        
        # 为东方财富接口配置限流：每分钟最多20次
        configure_domain_limit("push2.eastmoney.com", max_requests=20, time_window=60)
    """
    config = RateLimitConfig(max_requests=max_requests, time_window=time_window)
    rate_limiter.set_domain_config(domain, config)
