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
    频率限制器，用于限制同一域名的请求频率
    """
    _lock = threading.Lock()
    _default_limit = 30
    _domain_limits = {}
    _request_history = {}
    _window_seconds = 60
    _instance_lock = threading.Lock()
    _instance = None

    def __init__(self):
        pass

    def __new__(cls, *args, **kwargs):
        if not hasattr(RateLimiter, "_instance"):
            with RateLimiter._instance_lock:
                if not hasattr(RateLimiter, "_instance"):
                    RateLimiter._instance = object.__new__(cls)

    @classmethod
    def set_default_limit(cls, limit):
        """
        设置默认的请求频率限制
        :param limit: 每分钟请求次数
        """
        with cls._lock:
            cls._default_limit = limit

    @classmethod
    def set_domain_limit(cls, domain, limit):
        """
        设置指定域名的请求频率限制
        :param domain: 域名
        :param limit: 每分钟请求次数
        """
        with cls._lock:
            cls._domain_limits[domain] = limit

    @classmethod
    def get_domain_limit(cls, domain):
        """
        获取指定域名的请求频率限制
        :param domain: 域名
        :return: 限制次数
        """
        with cls._lock:
            return cls._domain_limits.get(domain, cls._default_limit)

    @classmethod
    def _clean_old_requests(cls, domain, current_time):
        """
        清理指定域名的旧请求记录
        :param domain: 域名
        :param current_time: 当前时间戳
        """
        if domain in cls._request_history:
            cls._request_history[domain] = [
                t for t in cls._request_history[domain]
                if current_time - t < cls._window_seconds
            ]

    @classmethod
    def check_and_wait(cls, url):
        """
        检查请求频率，如果超过限制则等待
        :param url: 请求URL
        """
        domain = cls._extract_domain(url)
        current_time = time.time()
        
        with cls._lock:
            cls._clean_old_requests(domain, current_time)
            limit = cls.get_domain_limit(domain)
            
            if domain not in cls._request_history:
                cls._request_history[domain] = []
            
            request_count = len(cls._request_history[domain])
            
            if request_count >= limit:
                oldest_request = cls._request_history[domain][0]
                wait_time = cls._window_seconds - (current_time - oldest_request)
                if wait_time > 0:
                    time.sleep(wait_time)
                cls._clean_old_requests(domain, time.time())
            
            cls._request_history[domain].append(time.time())

    @classmethod
    def _extract_domain(cls, url):
        """
        从URL中提取域名
        :param url: 请求URL
        :return: 域名
        """
        parsed = urlparse(url)
        return parsed.netloc


class SunRequests(object):
    def __init__(self, sun_proxy: SunProxy = None) -> None:
        super().__init__()
        self.sun_proxy = sun_proxy

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
        # 1. 频率限制检查
        if url:
            RateLimiter.check_and_wait(url)
        # 2. 获取设置代理
        proxies = self.__get_proxies(proxies)
        # 3. 请求数据结果
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

    def set_rate_limit(self, domain=None, limit=30):
        """
        设置请求频率限制
        :param domain: 域名，不传则设置默认限制
        :param limit: 每分钟请求次数
        """
        if domain:
            RateLimiter.set_domain_limit(domain, limit)
        else:
            RateLimiter.set_default_limit(limit)


sun_requests = SunRequests()
