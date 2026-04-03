# -*- coding: utf-8 -*-
"""
代理:https://jahttp.zhimaruanjian.com/getapi/

@desc: adata 请求工具类
@author: 1nchaos
@time:2023/3/30
@log: 封装请求次数
"""

import threading
import time
from urllib.parse import urlparse

import requests


class SunProxy(object):
    _data = {}
    _instance_lock = threading.Lock()

    def __init__(self):
        pass

    def __new__(cls, *args, **kwargs):
        if not hasattr(SunProxy, "_instance"):
            with SunProxy._instance_lock:
                if not hasattr(SunProxy, "_instance"):
                    SunProxy._instance = object.__new__(cls)

    @classmethod
    def set(cls, key, value):
        cls._data[key] = value

    @classmethod
    def get(cls, key):
        return cls._data.get(key)

    @classmethod
    def delete(cls, key):
        if key in cls._data:
            del cls._data[key]


class RateLimiter(object):
    """
    频率限制器，按域名控制请求频率
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if RateLimiter._instance is None:
            with RateLimiter._instance_lock:
                if RateLimiter._instance is None:
                    RateLimiter._instance = object.__new__(cls)
        return RateLimiter._instance

    def __init__(self, default_max_requests=30, time_window=60):
        """
        初始化频率限制器
        :param default_max_requests: 默认每分钟最大请求数
        :param time_window: 时间窗口（秒），默认60秒
        """
        if not hasattr(self, '_initialized'):
            self._default_max_requests = default_max_requests
            self._time_window = time_window
            # 存储每个域名的请求时间戳列表 {host: [timestamp1, timestamp2, ...]}
            self._requests_record = {}
            self._custom_limits = {}  # 存储自定义限制 {host: max_requests}
            self._lock = threading.Lock()
            self._initialized = True

    def set_default_limit(self, max_requests_per_minute):
        """
        设置默认的频率限制
        :param max_requests_per_minute: 每分钟最大请求数
        """
        self._default_max_requests = max_requests_per_minute

    def set_host_limit(self, host, max_requests_per_minute):
        """
        为特定域名设置频率限制
        :param host: 域名，例如 'api.example.com'
        :param max_requests_per_minute: 每分钟最大请求数
        """
        self._custom_limits[host] = max_requests_per_minute

    def _get_host_limit(self, host):
        """
        获取指定域名的频率限制
        """
        return self._custom_limits.get(host, self._default_max_requests)

    def _get_host(self, url):
        """
        从URL中提取域名
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return url

    def acquire(self, url):
        """
        获取请求许可，如果达到限制则等待
        :param url: 请求的URL
        :return: 实际等待的时间（秒）
        """
        host = self._get_host(url)
        max_requests = self._get_host_limit(host)

        with self._lock:
            now = time.time()

            # 初始化该域名的记录
            if host not in self._requests_record:
                self._requests_record[host] = []

            # 清理过期的记录（超出时间窗口的）
            cutoff_time = now - self._time_window
            self._requests_record[host] = [
                ts for ts in self._requests_record[host] if ts > cutoff_time
            ]

            # 检查是否达到限制
            if len(self._requests_record[host]) >= max_requests:
                # 需要等待的时间 = 最早请求的时间 + 时间窗口 - 当前时间
                wait_time = self._requests_record[host][0] + self._time_window - now
                if wait_time > 0:
                    # 释放锁后再等待，避免阻塞其他域名的请求
                    pass
                else:
                    wait_time = 0
            else:
                wait_time = 0

        # 在锁外等待
        if wait_time > 0:
            time.sleep(wait_time)
            now = time.time()

        # 记录本次请求
        with self._lock:
            self._requests_record[host].append(now)

        return wait_time


class SunRequests(object):
    def __init__(self, sun_proxy: SunProxy = None) -> None:
        super().__init__()
        self.sun_proxy = sun_proxy
        self._rate_limiter = RateLimiter()

    def set_rate_limit(self, max_requests_per_minute):
        """
        设置默认的频率限制（每分钟请求数）
        :param max_requests_per_minute: 每分钟最大请求数，默认30
        """
        self._rate_limiter.set_default_limit(max_requests_per_minute)

    def set_host_rate_limit(self, host, max_requests_per_minute):
        """
        为特定域名设置频率限制
        :param host: 域名，例如 'api.example.com'
        :param max_requests_per_minute: 每分钟最大请求数
        """
        self._rate_limiter.set_host_limit(host, max_requests_per_minute)

    def request(self, method='get', url=None, times=3, retry_wait_time=1588, proxies=None, wait_time=None, **kwargs):
        """
        简单封装的请求，参考requests，增加循环次数和次数之间的等待时间
        :param proxies: 代理配置
        :param method: 请求方法： get；post
        :param url: url
        :param times: 次数，int
        :param retry_wait_time: 重试等待时间，毫秒
        :param wait_time: 等待时间：毫秒；表示每个请求的间隔时间，在请求之前等待sleep，主要用于防止请求太频繁的限制。
        :param kwargs: 其它 requests 参数，用法相同
        :return: res
        """
        # 0. 频率限制检查
        self._rate_limiter.acquire(url)

        # 1. 获取设置代理
        proxies = self.__get_proxies(proxies)
        # 2. 请求数据结果
        res = None
        for i in range(times):
            if wait_time:
                time.sleep(wait_time / 1000)
            res = requests.request(method=method, url=url, proxies=proxies, **kwargs)
            if res.status_code in (200, 404):
                return res
            time.sleep(retry_wait_time / 1000)
            if i == times - 1:
                return res
        return res

    def __get_proxies(self, proxies):
        """
        获取代理配置
        """
        if proxies is None:
            proxies = {}
        is_proxy = SunProxy.get('is_proxy')
        ip = SunProxy.get('ip')
        proxy_url = SunProxy.get('proxy_url')
        if not ip and is_proxy and proxy_url:
            ip = requests.get(url=proxy_url).text.replace('\r\n', '') \
                .replace('\r', '').replace('\n', '').replace('\t', '')
        if is_proxy and ip:
            proxies = {'https': f"http://{ip}", 'http': f"http://{ip}"}
        return proxies


sun_requests = SunRequests()
