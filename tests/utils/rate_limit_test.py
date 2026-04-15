# -*- coding: utf-8 -*-
"""
@desc: 请求限流功能测试
@author: 1nchaos
@time: 2026/4/15
"""

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from adata.common.utils.rate_limit_config import RateLimitConfig
from adata.common.utils.rate_limiter import RateLimiter, rate_limiter


class RateLimiterTest(unittest.TestCase):
    """限流器核心功能测试"""

    def setUp(self):
        """测试前重置限流器状态"""
        RateLimiter.reset_instance()
        RateLimitConfig._config_loaded = False
        self.limiter = RateLimiter(default_limit=5, default_window=2)

    def test_extract_domain(self):
        """测试从URL提取域名功能"""
        test_cases = [
            ('https://push2.eastmoney.com/api/qt/stock/get', 'push2.eastmoney.com'),
            ('http://finance.pae.baidu.com/getfinance?code=1', 'finance.pae.baidu.com'),
            ('https://stock.xueqiu.com/v5/stock/quote.json', 'stock.xueqiu.com'),
        ]
        for url, expected_domain in test_cases:
            domain = self.limiter.extract_domain(url)
            self.assertEqual(domain, expected_domain, f"URL: {url}")

    def test_extract_domain_should_ignore_port(self):
        """测试提取域名时应忽略URL中的端口号"""
        url = 'https://api.test.com:8443/data'
        domain = self.limiter.extract_domain(url)
        self.assertEqual(domain, 'api.test.com')

    def test_extract_domain_invalid_url_returns_unknown(self):
        """测试异常URL场景返回unknown域名"""
        test_cases = [
            '',
            'not-a-url',
            '/local/path',
        ]
        for url in test_cases:
            domain = self.limiter.extract_domain(url)
            self.assertEqual(domain, 'unknown', f"URL: {url}")

    def test_domain_limit_config(self):
        """测试域名限流配置功能"""
        self.limiter.set_domain_limit('api.test.com', 10, 30)
        limit, window = self.limiter.get_domain_config('api.test.com')
        self.assertEqual(limit, 10)
        self.assertEqual(window, 30)

        limit, window = self.limiter.get_domain_config('unknown.com')
        self.assertEqual(limit, 5)
        self.assertEqual(window, 2)

    def test_try_acquire_success(self):
        """测试限流内请求成功"""
        url = 'https://api.test.com/data'
        for i in range(5):
            result = self.limiter.try_acquire(url, block=False)
            self.assertTrue(result, f"第{i+1}次请求应成功")

    def test_try_acquire_fail(self):
        """测试超出限流请求失败"""
        url = 'https://api.test.com/data'
        for i in range(5):
            self.limiter.try_acquire(url, block=False)

        result = self.limiter.try_acquire(url, block=False)
        self.assertFalse(result, "第6次请求应失败")

    def test_domain_limit_should_apply_when_url_contains_port(self):
        """测试带端口URL也应命中域名限流配置"""
        self.limiter.set_domain_limit('api.test.com', 1, 60)
        first_result = self.limiter.try_acquire('https://api.test.com:8443/data', block=False)
        second_result = self.limiter.try_acquire('https://api.test.com:8443/data', block=False)
        self.assertTrue(first_result, "首次请求应成功")
        self.assertFalse(second_result, "同域名第二次请求应被限流")

    def test_subdomains_should_use_independent_limits(self):
        """测试不同子域名应使用各自独立的限流桶"""
        self.limiter.set_domain_limit('a.api.test.com', 1, 60)
        self.limiter.set_domain_limit('b.api.test.com', 1, 60)
        first_subdomain_result = self.limiter.try_acquire('https://a.api.test.com/data', block=False)
        second_subdomain_result = self.limiter.try_acquire('https://b.api.test.com/data', block=False)
        self.assertTrue(first_subdomain_result, "子域名a首次请求应成功")
        self.assertTrue(second_subdomain_result, "子域名b首次请求应成功")

    def test_sliding_window_reset(self):
        """测试滑动窗口时间重置"""
        url = 'https://api.test.com/data'
        for i in range(5):
            self.limiter.try_acquire(url, block=False)

        time.sleep(2.1)

        result = self.limiter.try_acquire(url, block=False)
        self.assertTrue(result, "时间窗口过后应重置计数")

    def test_blocking_acquire(self):
        """测试阻塞等待获取许可"""
        url = 'https://api.test.com/data'
        for i in range(5):
            self.limiter.try_acquire(url, block=False)

        start_time = time.time()
        result = self.limiter.try_acquire(url, block=True)
        wait_time = time.time() - start_time

        self.assertTrue(result)
        self.assertGreaterEqual(wait_time, 0, "应等待至少0秒")


class ConcurrentRateLimitTest(unittest.TestCase):
    """并发场景下限流测试"""

    def setUp(self):
        """测试前重置限流器"""
        RateLimiter.reset_instance()
        RateLimitConfig._config_loaded = False
        self.limiter = RateLimiter(default_limit=10, default_window=5)
        self.counter = 0
        self.lock = threading.Lock()

    def test_concurrent_request_safety(self):
        """测试多线程并发限流准确性"""
        url = 'https://api.test.com/concurrent'
        thread_count = 50

        def request_task():
            if self.limiter.try_acquire(url, block=False):
                with self.lock:
                    self.counter += 1
                return True
            return False

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(request_task) for _ in range(thread_count)]
            results = [future.result() for future in as_completed(futures)]

        success_count = sum(1 for r in results if r)
        self.assertEqual(success_count, 10, f"应只允许10次请求，实际成功{success_count}次")
        self.assertEqual(self.counter, 10, "计数器应与成功次数一致")


class RateLimitConfigTest(unittest.TestCase):
    """配置管理测试"""

    def test_load_default_config(self):
        """测试默认配置加载"""
        RateLimitConfig._config_loaded = False
        RateLimitConfig.load_config()
        config = RateLimitConfig.get_current_config()

        self.assertIn('default', config)
        self.assertIn('domains', config)
        self.assertGreater(len(config['domains']), 0)

    def test_get_current_config(self):
        """测试获取当前配置"""
        RateLimitConfig._config_loaded = False
        RateLimitConfig.load_config()
        config = RateLimitConfig.get_current_config()

        self.assertIsInstance(config['default']['limit'], int)
        self.assertIsInstance(config['default']['window'], int)
        self.assertIsInstance(config['domains'], dict)


def run_benchmark():
    """性能基准测试"""
    print("\n=== 限流功能性能测试 ===")
    limiter = RateLimiter(default_limit=1000, default_window=60)
    limiter._request_records.clear()

    url = 'https://benchmark.test.com/api'
    start_time = time.time()

    for i in range(1000):
        limiter.try_acquire(url, block=False)

    elapsed = time.time() - start_time
    print(f"1000次限流检查耗时: {elapsed:.4f}秒")
    print(f"平均每次耗时: {elapsed * 1000:.4f}毫秒")


if __name__ == '__main__':
    print("=== 开始执行限流功能测试 ===")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(RateLimiterTest))
    suite.addTests(loader.loadTestsFromTestCase(ConcurrentRateLimitTest))
    suite.addTests(loader.loadTestsFromTestCase(RateLimitConfigTest))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    run_benchmark()

    print("\n=== 测试完成 ===")
    if result.wasSuccessful():
        print("[OK] 所有测试通过!")
    else:
        print(f"[FAIL] 测试失败: {len(result.failures)}个失败, {len(result.errors)}个错误")
