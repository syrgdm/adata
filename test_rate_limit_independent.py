# -*- coding: utf-8 -*-
"""
独立测试频率限制功能
"""
import threading
import time
from urllib.parse import urlparse


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
            
            print(f"[{time.strftime('%H:%M:%S')}] 域名: {domain}, 当前请求数: {request_count}/{limit}")
            
            if request_count >= limit:
                oldest_request = cls._request_history[domain][0]
                wait_time = cls._window_seconds - (current_time - oldest_request)
                if wait_time > 0:
                    print(f"  超过限制，需要等待 {wait_time:.1f} 秒")
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


def test_rate_limiter():
    """
    测试 RateLimiter 功能
    """
    print("=" * 60)
    print("开始测试 RateLimiter 频率限制功能")
    print("=" * 60)
    
    # 测试设置默认限制
    RateLimiter.set_default_limit(5)
    print(f"\n默认限制已设置为 5 次/分钟")
    
    # 测试设置指定域名限制
    RateLimiter.set_domain_limit("example.com", 10)
    print("example.com 限制已设置为 10 次/分钟")
    
    # 测试获取限制
    print(f"\nexample.com 的限制: {RateLimiter.get_domain_limit('example.com')}")
    print(f"other.com 的限制: {RateLimiter.get_domain_limit('other.com')}")
    
    # 快速发送请求测试
    test_url = "https://www.example.com"
    print(f"\n{'=' * 60}")
    print(f"开始对 {test_url} 发送请求测试")
    print(f"{'=' * 60}")
    
    start_time = time.time()
    
    # 发送 12 次请求
    for i in range(12):
        RateLimiter.check_and_wait(test_url)
    
    end_time = time.time()
    print(f"\n{'=' * 60}")
    print(f"测试完成，总耗时: {end_time - start_time:.2f} 秒")
    print(f"{'=' * 60}")
    
    # 恢复默认限制
    RateLimiter.set_default_limit(30)
    print("\n默认限制已恢复为 30 次/分钟")


if __name__ == "__main__":
    test_rate_limiter()
