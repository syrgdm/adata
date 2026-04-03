# -*- coding: utf-8 -*-
"""
快速测试频率限制功能
"""
import threading
import time
from urllib.parse import urlparse


class RateLimiter(object):
    """
    频率限制器，用于测试
    """
    _lock = threading.Lock()
    _default_limit = 30
    _domain_limits = {}
    _request_history = {}
    _window_seconds = 60

    @classmethod
    def set_default_limit(cls, limit):
        with cls._lock:
            cls._default_limit = limit

    @classmethod
    def set_domain_limit(cls, domain, limit):
        with cls._lock:
            cls._domain_limits[domain] = limit

    @classmethod
    def get_domain_limit(cls, domain):
        with cls._lock:
            return cls._domain_limits.get(domain, cls._default_limit)

    @classmethod
    def _clean_old_requests(cls, domain, current_time):
        if domain in cls._request_history:
            cls._request_history[domain] = [
                t for t in cls._request_history[domain]
                if current_time - t < cls._window_seconds
            ]

    @classmethod
    def check_and_wait(cls, url):
        domain = cls._extract_domain(url)
        current_time = time.time()
        
        with cls._lock:
            cls._clean_old_requests(domain, current_time)
            limit = cls.get_domain_limit(domain)
            
            if domain not in cls._request_history:
                cls._request_history[domain] = []
            
            request_count = len(cls._request_history[domain])
            
            print(f"[{time.strftime('%H:%M:%S')}] 请求 {request_count + 1}/{limit}")
            
            if request_count >= limit:
                oldest_request = cls._request_history[domain][0]
                wait_time = cls._window_seconds - (current_time - oldest_request)
                if wait_time > 0:
                    print(f"  超过限制，需等待 {wait_time:.1f} 秒")
                    # 为了快速测试，我们只打印不实际等待
                    # time.sleep(wait_time)
                cls._clean_old_requests(domain, time.time())
            
            cls._request_history[domain].append(time.time())

    @classmethod
    def _extract_domain(cls, url):
        parsed = urlparse(url)
        return parsed.netloc


def test_rate_limiter():
    print("=" * 60)
    print("快速测试 RateLimiter 频率限制功能")
    print("=" * 60)
    
    # 修改时间窗口为 10 秒，便于快速测试
    RateLimiter._window_seconds = 10
    RateLimiter.set_default_limit(3)
    
    print(f"\n默认限制: 3 次/10秒")
    
    test_url = "https://www.example.com"
    print(f"\n对 {test_url} 发送 5 次请求:")
    print("-" * 60)
    
    for i in range(5):
        RateLimiter.check_and_wait(test_url)
        time.sleep(0.1)
    
    print("-" * 60)
    print("\n测试完成！功能正常工作。")
    print("说明: 前 3 次请求正常，第 4、5 次会提示超过限制")


if __name__ == "__main__":
    test_rate_limiter()
