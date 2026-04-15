# -*- coding: utf-8 -*-
"""
@desc: 限流器单元测试
@author: 1nchaos
@time: 2024/1/1
@log: 验证滑动窗口限流功能
"""

import threading
import time
import unittest

from adata.common.utils.rate_limiter import (
    RateLimitConfig,
    DomainRateLimiter,
    RateLimiterManager,
    rate_limiter_manager,
    rate_limit_config
)


class TestRateLimitConfig(unittest.TestCase):
    """限流配置类测试"""
    
    def setUp(self):
        self.config = RateLimitConfig()
        self.config._domain_configs.clear()
    
    def test_default_config(self):
        """测试默认配置"""
        self.assertEqual(self.config.default_max_requests, 30)
        self.assertEqual(self.config.default_window_seconds, 60)
    
    def test_set_default(self):
        """测试设置默认配置"""
        self.config.set_default(50, 120)
        self.assertEqual(self.config.default_max_requests, 50)
        self.assertEqual(self.config.default_window_seconds, 120)
    
    def test_domain_config(self):
        """测试域名差异化配置"""
        self.config.set_domain_config('api.example.com', 100, 30)
        max_req, window = self.config.get_domain_config('api.example.com')
        self.assertEqual(max_req, 100)
        self.assertEqual(window, 30)
        
        max_req, window = self.config.get_domain_config('other.example.com')
        self.assertEqual(max_req, 30)
        self.assertEqual(window, 60)
    
    def test_enabled(self):
        """测试启用/禁用限流"""
        self.assertTrue(self.config.enabled)
        self.config.set_enabled(False)
        self.assertFalse(self.config.enabled)
        self.config.set_enabled(True)


class TestDomainRateLimiter(unittest.TestCase):
    """域名限流器测试"""
    
    def test_basic_limit(self):
        """测试基本限流功能"""
        limiter = DomainRateLimiter(max_requests=3, window_seconds=1)
        
        self.assertEqual(limiter.acquire(), 0.0)
        self.assertEqual(limiter.acquire(), 0.0)
        self.assertEqual(limiter.acquire(), 0.0)
        
        wait_time = limiter.acquire()
        self.assertGreater(wait_time, 0)
    
    def test_window_slide(self):
        """测试滑动窗口"""
        limiter = DomainRateLimiter(max_requests=2, window_seconds=0.5)
        
        limiter.acquire()
        limiter.acquire()
        
        wait_time = limiter.acquire()
        self.assertGreater(wait_time, 0)
        
        time.sleep(0.6)
        
        wait_time = limiter.acquire()
        self.assertEqual(wait_time, 0.0)
    
    def test_current_count(self):
        """测试当前计数"""
        limiter = DomainRateLimiter(max_requests=5, window_seconds=1)
        
        self.assertEqual(limiter.current_count, 0)
        limiter.acquire()
        self.assertEqual(limiter.current_count, 1)
        limiter.acquire()
        self.assertEqual(limiter.current_count, 2)


class TestRateLimiterManager(unittest.TestCase):
    """限流器管理器测试"""
    
    def setUp(self):
        self.manager = RateLimiterManager()
        self.manager.clear_all_limiters()
        self.manager.config._domain_configs.clear()
        self.manager.config.set_default(30, 60)
    
    def test_extract_domain(self):
        """测试域名提取"""
        self.assertEqual(
            self.manager._extract_domain('https://api.example.com/path'),
            'api.example.com'
        )
        self.assertEqual(
            self.manager._extract_domain('http://test.com:8080/api'),
            'test.com'
        )
        self.assertEqual(self.manager._extract_domain(''), '')
    
    def test_different_domains_independent(self):
        """测试不同域名独立限流"""
        self.manager.config.set_default(2, 1)
        
        self.manager.before_request('https://domain1.com/api')
        self.manager.before_request('https://domain1.com/api')
        self.manager.before_request('https://domain2.com/api')
        self.manager.before_request('https://domain2.com/api')
        
        wait_time1 = self.manager.get_wait_time('https://domain1.com/api')
        wait_time2 = self.manager.get_wait_time('https://domain2.com/api')
        
        self.assertGreater(wait_time1, 0)
        self.assertGreater(wait_time2, 0)
    
    def test_disabled_rate_limit(self):
        """测试禁用限流"""
        self.manager.config.set_enabled(False)
        self.manager.config.set_default(1, 1)
        
        self.manager.before_request('https://test.com/api')
        self.manager.before_request('https://test.com/api')
        
        wait_time = self.manager.get_wait_time('https://test.com/api')
        self.assertEqual(wait_time, 0.0)
        
        self.manager.config.set_enabled(True)


class TestConcurrency(unittest.TestCase):
    """并发测试"""
    
    def test_thread_safety(self):
        """测试线程安全"""
        limiter = DomainRateLimiter(max_requests=10, window_seconds=1)
        results = []
        
        def make_request():
            wait_time = limiter.acquire()
            results.append(wait_time)
        
        threads = [threading.Thread(target=make_request) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        zero_wait_count = sum(1 for w in results if w == 0)
        self.assertEqual(zero_wait_count, 10)


if __name__ == '__main__':
    unittest.main()
