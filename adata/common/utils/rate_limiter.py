# -*- coding: utf-8 -*-
"""
@desc: 请求速率限制器 - 基于滑动窗口算法实现轻量级限流
@author: 1nchaos
@time: 2026/4/15
"""

import threading
import time
from collections import defaultdict, deque
from typing import Optional, Tuple
from urllib.parse import urlparse


class RateLimiter:
    """
    基于滑动窗口算法的请求速率限制器
    支持按域名隔离限流，线程安全
    """

    _instance: Optional['RateLimiter'] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式，确保全局唯一限流器实例"""
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(self, default_limit: int = 30, default_window: int = 60):
        """
        初始化限流器
        :param default_limit: 默认限流次数
        :param default_window: 默认时间窗口（秒）
        """
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self.default_limit = default_limit
        self.default_window = default_window
        self._domain_configs = {}
        self._request_records = defaultdict(deque)
        self._lock = threading.Lock()

    def set_domain_limit(self, domain: str, limit: int, window: int):
        """
        设置指定域名的限流规则
        :param domain: 目标域名（如 api.example.com）
        :param limit: 时间窗口内最大请求次数
        :param window: 时间窗口（秒）
        """
        with self._lock:
            self._domain_configs[domain] = {
                'limit': limit,
                'window': window
            }

    def get_domain_config(self, domain: str) -> Tuple[int, int]:
        """
        获取指定域名的限流配置，不存在则返回默认值
        :param domain: 目标域名
        :return: (limit, window)
        """
        config = self._domain_configs.get(domain)
        if config:
            return config['limit'], config['window']
        return self.default_limit, self.default_window

    @staticmethod
    def extract_domain(url: str) -> str:
        """
        从URL中提取域名
        :param url: 请求URL
        :return: 域名
        """
        parsed = urlparse(url)
        return parsed.netloc or 'unknown'

    def _clean_expired(self, domain: str, window: int, current_time: float):
        """
        清理过期的请求记录
        :param domain: 目标域名
        :param window: 时间窗口（秒）
        :param current_time: 当前时间戳
        """
        records = self._request_records[domain]
        expire_time = current_time - window
        while records and records[0] <= expire_time:
            records.popleft()

    def try_acquire(self, url: str, block: bool = True) -> bool:
        """
        尝试获取请求许可
        :param url: 请求URL
        :param block: 是否阻塞等待直到获取许可
        :return: 是否获取成功
        """
        domain = self.extract_domain(url)

        while True:
            with self._lock:
                limit, window = self.get_domain_config(domain)
                current_time = time.time()
                self._clean_expired(domain, window, current_time)
                records = self._request_records[domain]

                if len(records) < limit:
                    records.append(current_time)
                    return True

                if not block:
                    return False

                next_available = records[0] + window - current_time

            if next_available > 0:
                time.sleep(min(next_available, 0.1))

    def acquire_with_wait_time(self, url: str) -> float:
        """
        获取请求许可并返回需要等待的时间
        :param url: 请求URL
        :return: 需要等待的时间（秒），0表示可以立即执行
        """
        domain = self.extract_domain(url)

        with self._lock:
            limit, window = self.get_domain_config(domain)
            current_time = time.time()
            self._clean_expired(domain, window, current_time)
            records = self._request_records[domain]

            if len(records) < limit:
                records.append(current_time)
                return 0

            next_available = records[0] + window - current_time
            return max(next_available, 0)

    def reset(self):
        """重置限流器状态，仅用于测试场景"""
        with self._lock:
            self._request_records.clear()
            self._domain_configs.clear()
            self.default_limit = 30
            self.default_window = 60

    @classmethod
    def reset_instance(cls):
        """重置单例实例"""
        with cls._instance_lock:
            cls._instance = None


rate_limiter = RateLimiter()
