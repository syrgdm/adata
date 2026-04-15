# -*- coding: utf-8 -*-
"""
@desc: 限流器单元测试
@author: 1nchaos
@time: 2026/4/15
@log: 测试限流器的各项功能
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from adata.common.utils.rate_limiter import (
    RateLimitConfig,
    SlidingWindowRateLimiter,
    configure_domain_limit,
    rate_limit_by_domain,
)


class TestRateLimitConfig(unittest.TestCase):
    """测试限流配置类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = RateLimitConfig()
        self.assertEqual(config.max_requests, 30)
        self.assertEqual(config.time_window, 60)
        self.assertIsNone(config.wait_timeout)
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = RateLimitConfig(max_requests=50, time_window=30, wait_timeout=10.0)
        self.assertEqual(config.max_requests, 50)
        self.assertEqual(config.time_window, 30)
        self.assertEqual(config.wait_timeout, 10.0)


class TestSlidingWindowRateLimiter(unittest.TestCase):
    """测试滑动窗口限流器"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_singleton(self):
        """测试单例模式"""
        limiter1 = SlidingWindowRateLimiter()
        limiter2 = SlidingWindowRateLimiter()
        self.assertIs(limiter1, limiter2)
    
    def test_get_domain(self):
        """测试域名提取"""
        test_cases = [
            ("https://api.example.com/data", "api.example.com"),
            ("http://push2.eastmoney.com/api/test", "push2.eastmoney.com"),
            ("https://API.EXAMPLE.COM/path", "api.example.com"),  # 测试大小写
            ("invalid_url", "invalid_url"),  # 无效URL
        ]
        
        for url, expected in test_cases:
            with self.subTest(url=url):
                result = self.limiter._get_domain(url)
                self.assertEqual(result, expected)
    
    def test_acquire_success(self):
        """测试成功获取许可"""
        url = "https://api-success.example.com/data"
        config = RateLimitConfig(max_requests=30, time_window=60)
        self.limiter.set_domain_config("api-success.example.com", config)
        
        # 前30次应该都能成功
        for i in range(30):
            result = self.limiter.acquire(url, blocking=False)
            self.assertTrue(result, f"第{i+1}次请求应该成功")
    
    def test_acquire_limit_reached(self):
        """测试达到限流阈值"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=5, time_window=60)
        self.limiter.set_domain_config("api.example.com", config)
        
        # 前5次应该成功
        for i in range(5):
            result = self.limiter.acquire(url, blocking=False)
            self.assertTrue(result, f"第{i+1}次请求应该成功")
        
        # 第6次应该失败（非阻塞模式）
        result = self.limiter.acquire(url, blocking=False)
        self.assertFalse(result, "第6次请求应该被限流")
    
    def test_try_acquire(self):
        """测试非阻塞获取许可"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=3, time_window=60)
        self.limiter.set_domain_config("api.example.com", config)
        
        # 前3次应该成功
        for i in range(3):
            self.assertTrue(self.limiter.try_acquire(url))
        
        # 第4次应该失败
        self.assertFalse(self.limiter.try_acquire(url))
    
    def test_time_window_expiration(self):
        """测试时间窗口过期后重置"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=2, time_window=1)  # 1秒窗口
        self.limiter.set_domain_config("api.example.com", config)
        
        # 使用2次额度
        self.assertTrue(self.limiter.try_acquire(url))
        self.assertTrue(self.limiter.try_acquire(url))
        self.assertFalse(self.limiter.try_acquire(url))  # 被限流
        
        # 等待时间窗口过期
        time.sleep(1.1)
        
        # 应该可以再次获取许可
        self.assertTrue(self.limiter.try_acquire(url))
    
    def test_get_current_count(self):
        """测试获取当前计数"""
        url = "https://api.example.com/data"
        
        self.assertEqual(self.limiter.get_current_count(url), 0)
        
        self.limiter.acquire(url, blocking=False)
        self.assertEqual(self.limiter.get_current_count(url), 1)
        
        self.limiter.acquire(url, blocking=False)
        self.assertEqual(self.limiter.get_current_count(url), 2)
    
    def test_get_remaining_quota(self):
        """测试获取剩余额度"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=10, time_window=60)
        self.limiter.set_domain_config("api.example.com", config)
        
        self.assertEqual(self.limiter.get_remaining_quota(url), 10)
        
        self.limiter.acquire(url, blocking=False)
        self.assertEqual(self.limiter.get_remaining_quota(url), 9)
        
        # 使用完所有额度
        for _ in range(9):
            self.limiter.acquire(url, blocking=False)
        self.assertEqual(self.limiter.get_remaining_quota(url), 0)
    
    def test_domain_isolation(self):
        """测试不同域名相互隔离"""
        url1 = "https://api1.example.com/data"
        url2 = "https://api2.example.com/data"
        config = RateLimitConfig(max_requests=3, time_window=60)
        
        self.limiter.set_domain_config("api1.example.com", config)
        self.limiter.set_domain_config("api2.example.com", config)
        
        # 使用api1的所有额度
        for _ in range(3):
            self.limiter.acquire(url1, blocking=False)
        
        # api1应该被限流
        self.assertFalse(self.limiter.try_acquire(url1))
        
        # api2应该仍然可用
        self.assertTrue(self.limiter.try_acquire(url2))
    
    def test_concurrent_access(self):
        """测试并发访问的线程安全性"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=100, time_window=60)
        self.limiter.set_domain_config("api.example.com", config)
        
        success_count = 0
        fail_count = 0
        
        def make_request():
            nonlocal success_count, fail_count
            if self.limiter.try_acquire(url):
                success_count += 1
            else:
                fail_count += 1
        
        # 使用多线程并发请求
        threads = []
        for _ in range(150):
            t = threading.Thread(target=make_request)
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # 成功次数应该等于限流阈值
        self.assertEqual(success_count, 100)
        self.assertEqual(fail_count, 50)
    
    def test_reset_single_domain(self):
        """测试重置单个域名"""
        url = "https://api.example.com/data"
        config = RateLimitConfig(max_requests=2, time_window=60)
        self.limiter.set_domain_config("api.example.com", config)
        
        # 使用所有额度
        self.limiter.acquire(url, blocking=False)
        self.limiter.acquire(url, blocking=False)
        self.assertFalse(self.limiter.try_acquire(url))
        
        # 重置
        self.limiter.reset(url)
        
        # 应该可以再次获取许可
        self.assertTrue(self.limiter.try_acquire(url))
    
    def test_reset_all_domains(self):
        """测试重置所有域名"""
        url1 = "https://api1.example.com/data"
        url2 = "https://api2.example.com/data"
        config = RateLimitConfig(max_requests=1, time_window=60)
        
        self.limiter.set_domain_config("api1.example.com", config)
        self.limiter.set_domain_config("api2.example.com", config)
        
        # 使用所有额度
        self.limiter.acquire(url1, blocking=False)
        self.limiter.acquire(url2, blocking=False)
        
        # 重置所有
        self.limiter.reset()
        
        # 两个域名都应该可以再次获取许可
        self.assertTrue(self.limiter.try_acquire(url1))
        self.assertTrue(self.limiter.try_acquire(url2))


class TestRateLimitDecorator(unittest.TestCase):
    """测试限流装饰器"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_decorator_basic(self):
        """测试装饰器基本功能"""
        call_count = 0
        
        @rate_limit_by_domain(max_requests=2, time_window=60)
        def fetch_data(url):
            nonlocal call_count
            call_count += 1
            return f"data from {url}"
        
        # 前2次应该成功执行
        result1 = fetch_data("https://api.example.com/1")
        result2 = fetch_data("https://api.example.com/2")
        
        self.assertEqual(result1, "data from https://api.example.com/1")
        self.assertEqual(result2, "data from https://api.example.com/2")
        self.assertEqual(call_count, 2)
    
    def test_decorator_with_url_extractor(self):
        """测试带URL提取器的装饰器"""
        call_count = 0
        
        @rate_limit_by_domain(
            max_requests=2,
            time_window=60,
            url_extractor=lambda api_url, **kwargs: api_url
        )
        def fetch_data(api_url=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"data from {api_url}"
        
        # 前2次应该成功
        fetch_data(api_url="https://api.example.com/1")
        fetch_data(api_url="https://api.example.com/2")
        
        self.assertEqual(call_count, 2)
    
    def test_configure_domain_limit(self):
        """测试配置域名限流"""
        # 配置特定域名的限流
        configure_domain_limit("special.api.com", max_requests=5, time_window=30)
        
        url = "https://special.api.com/data"
        
        # 前5次应该成功
        for i in range(5):
            result = self.limiter.try_acquire(url)
            self.assertTrue(result, f"第{i+1}次请求应该成功")
        
        # 第6次应该失败
        self.assertFalse(self.limiter.try_acquire(url))


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_real_world_scenario(self):
        """
        模拟真实场景：批量获取股票数据
        测试在批量请求场景下，限流器是否能有效防止触发风控
        """
        # 配置测试域名限流：每秒最多2次（用于快速测试）
        test_domain = "api.test.example.com"
        configure_domain_limit(test_domain, max_requests=2, time_window=1)
        
        request_times = []
        
        @rate_limit_by_domain(
            max_requests=2, 
            time_window=1,
            url_extractor=lambda stock_code, **kwargs: f"https://{test_domain}/data/{stock_code}"
        )
        def fetch_stock_data(stock_code):
            # 模拟请求
            request_times.append(time.time())
            return {"code": stock_code, "price": 10.0}
        
        # 模拟批量获取10只股票数据
        stock_codes = [f"{i:06d}" for i in range(1, 11)]
        
        start_time = time.time()
        
        # 使用线程池模拟并发请求
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_stock_data, code) for code in stock_codes]
            results = [f.result() for f in as_completed(futures)]
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证所有请求都成功完成
        self.assertEqual(len(results), 10)
        
        # 验证限流生效：10次请求，每秒2次，至少需要4秒
        # 由于使用了阻塞等待模式，总时间应该大于等于4秒
        self.assertGreaterEqual(
            total_time, 4,
            f"10次请求限流为每秒2次，总时间应该>=4秒，实际为{total_time:.2f}秒"
        )
        
        # 验证在任意1秒窗口内，请求次数不超过2次
        for i in range(len(request_times)):
            window_start = request_times[i]
            window_end = window_start + 1
            count_in_window = sum(1 for t in request_times if window_start <= t < window_end)
            self.assertLessEqual(
                count_in_window, 2,
                f"在1秒窗口内有{count_in_window}次请求，超过限流阈值2"
            )


if __name__ == '__main__':
    unittest.main()
