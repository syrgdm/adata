# -*- coding: utf-8 -*-
"""
@desc: 频率限制功能测试
@author: 1nchaos
@time: 2024/4/3
@log: 测试 RateLimiter 和 SunRequests 的频率限制功能
"""
import time
import unittest
from unittest.mock import patch, MagicMock

import adata
from adata.common.utils.sunrequests import RateLimiter, SunRequests, sun_requests


class RateLimiterTestCase(unittest.TestCase):
    """RateLimiter 类的单元测试"""

    @classmethod
    def setUpClass(cls) -> None:
        print("----STAR执行：频率限制：单元测试STAR----")

    @classmethod
    def tearDownClass(cls) -> None:
        print("----END执行：频率限制：单元测试END----")

    def setUp(self):
        """每个测试用例前重置 RateLimiter 实例"""
        # 重置单例状态
        limiter = RateLimiter()
        limiter._requests_record = {}
        limiter._custom_limits = {}
        limiter._default_max_requests = 30
        limiter._time_window = 60

    def tearDown(self):
        pass

    def test_singleton(self):
        """测试 RateLimiter 是单例模式"""
        limiter1 = RateLimiter()
        limiter2 = RateLimiter()
        self.assertEqual(id(limiter1), id(limiter2))
        print("测试通过：RateLimiter 是单例模式")

    def test_get_host_from_url(self):
        """测试从 URL 中提取域名"""
        limiter = RateLimiter()
        test_cases = [
            ("http://push2.eastmoney.com/api/test", "push2.eastmoney.com"),
            ("https://api.example.com:8080/path", "api.example.com:8080"),
            ("http://localhost/test", "localhost"),
            ("https://stock.xueqiu.com/v5/stock", "stock.xueqiu.com"),
        ]
        for url, expected_host in test_cases:
            host = limiter._get_host(url)
            self.assertEqual(host, expected_host)
        print("测试通过：URL 域名提取正确")

    def test_default_limit(self):
        """测试默认频率限制"""
        limiter = RateLimiter()
        self.assertEqual(limiter._default_max_requests, 30)

        # 设置新的默认限制
        limiter.set_default_limit(50)
        self.assertEqual(limiter._default_max_requests, 50)
        print("测试通过：默认频率限制设置正确")

    def test_host_specific_limit(self):
        """测试特定域名的频率限制"""
        limiter = RateLimiter()
        limiter.set_host_limit("test.example.com", 10)

        # 检查自定义限制
        self.assertEqual(limiter._get_host_limit("test.example.com"), 10)
        # 未设置的域名使用默认限制
        self.assertEqual(limiter._get_host_limit("other.com"), 30)
        print("测试通过：特定域名频率限制设置正确")

    def test_acquire_within_limit(self):
        """测试在限制范围内的请求"""
        limiter = RateLimiter()
        limiter.set_default_limit(5)

        url = "http://test.example.com/api"
        # 5 次请求应该都通过，不需要等待
        for i in range(5):
            wait_time = limiter.acquire(url)
            self.assertEqual(wait_time, 0)
        print("测试通过：限制范围内的请求正常通过")

    def test_acquire_exceeds_limit(self):
        """测试超过限制时的等待行为"""
        limiter = RateLimiter()
        limiter.set_default_limit(2)
        limiter._time_window = 1  # 1秒时间窗口，方便测试

        url = "http://test.example.com/api"

        # 前 2 次请求应该不需要等待
        self.assertEqual(limiter.acquire(url), 0)
        self.assertEqual(limiter.acquire(url), 0)

        # 第 3 次请求应该需要等待（但因为我们刚请求完，可能需要等待接近 1 秒）
        start_time = time.time()
        wait_time = limiter.acquire(url)
        elapsed = time.time() - start_time

        # 验证确实发生了等待
        self.assertGreater(elapsed, 0.5)
        print(f"测试通过：超过限制时正确等待，等待时间: {elapsed:.2f}秒")

    def test_different_hosts_independent(self):
        """测试不同域名的限制是独立的"""
        limiter = RateLimiter()
        limiter.set_default_limit(2)

        url1 = "http://host1.com/api"
        url2 = "http://host2.com/api"

        # 每个域名都可以请求 2 次而不需要等待
        for i in range(2):
            self.assertEqual(limiter.acquire(url1), 0)
            self.assertEqual(limiter.acquire(url2), 0)
        print("测试通过：不同域名的限制相互独立")


class SunRequestsRateLimitTestCase(unittest.TestCase):
    """SunRequests 频率限制集成测试"""

    @classmethod
    def setUpClass(cls) -> None:
        print("----STAR执行：SunRequests 频率限制：集成测试STAR----")

    @classmethod
    def tearDownClass(cls) -> None:
        print("----END执行：SunRequests 频率限制：集成测试END----")

    def setUp(self):
        """重置频率限制器状态"""
        limiter = RateLimiter()
        limiter._requests_record = {}
        limiter._custom_limits = {}
        limiter._default_max_requests = 30
        limiter._time_window = 60

    def test_set_rate_limit(self):
        """测试设置全局频率限制"""
        sun_requests.set_rate_limit(60)
        self.assertEqual(sun_requests._rate_limiter._default_max_requests, 60)

        # 恢复默认值
        sun_requests.set_rate_limit(30)
        print("测试通过：全局频率限制设置正确")

    def test_set_host_rate_limit(self):
        """测试设置特定域名频率限制"""
        sun_requests.set_host_rate_limit("api.example.com", 100)
        self.assertEqual(
            sun_requests._rate_limiter._custom_limits.get("api.example.com"), 100
        )
        print("测试通过：特定域名频率限制设置正确")

    @patch('adata.common.utils.sunrequests.requests.request')
    def test_request_with_rate_limit(self, mock_request):
        """测试请求时应用频率限制"""
        # 模拟请求响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        # 设置较低的限制以便测试
        sun_requests.set_rate_limit(1000)  # 设置一个较高的限制，避免实际等待

        # 执行请求
        start_time = time.time()
        for i in range(3):
            sun_requests.request(url="http://test.com/api")
        elapsed = time.time() - start_time

        # 验证请求被调用
        self.assertEqual(mock_request.call_count, 3)
        print(f"测试通过：请求时应用频率限制，3次请求耗时: {elapsed:.2f}秒")


class AdataApiRateLimitTestCase(unittest.TestCase):
    """通过 adata 模块 API 测试频率限制"""

    @classmethod
    def setUpClass(cls) -> None:
        print("----STAR执行：adata API 频率限制：测试STAR----")

    @classmethod
    def tearDownClass(cls) -> None:
        print("----END执行：adata API 频率限制：测试END----")

    def setUp(self):
        """重置频率限制器状态"""
        limiter = RateLimiter()
        limiter._requests_record = {}
        limiter._custom_limits = {}
        limiter._default_max_requests = 30
        limiter._time_window = 60

    def test_adata_set_rate_limit(self):
        """测试通过 adata 模块设置全局频率限制"""
        adata.set_rate_limit(50)
        self.assertEqual(sun_requests._rate_limiter._default_max_requests, 50)

        # 恢复默认值
        adata.set_rate_limit(30)
        print("测试通过：adata.set_rate_limit 工作正常")

    def test_adata_set_host_rate_limit(self):
        """测试通过 adata 模块设置特定域名频率限制"""
        adata.set_host_rate_limit("push2.eastmoney.com", 60)
        self.assertEqual(
            sun_requests._rate_limiter._custom_limits.get("push2.eastmoney.com"), 60
        )
        print("测试通过：adata.set_host_rate_limit 工作正常")


class RateLimiterPerformanceTestCase(unittest.TestCase):
    """频率限制性能测试"""

    @classmethod
    def setUpClass(cls) -> None:
        print("----STAR执行：频率限制：性能测试STAR----")

    @classmethod
    def tearDownClass(cls) -> None:
        print("----END执行：频率限制：性能测试END----")

    def setUp(self):
        """重置频率限制器状态"""
        limiter = RateLimiter()
        limiter._requests_record = {}
        limiter._custom_limits = {}
        limiter._default_max_requests = 30
        limiter._time_window = 60

    def test_high_frequency_requests(self):
        """测试高频请求场景"""
        limiter = RateLimiter()
        limiter.set_default_limit(1000)  # 设置高限制

        url = "http://test.com/api"
        start_time = time.time()

        # 快速发起 100 次请求
        for i in range(100):
            limiter.acquire(url)

        elapsed = time.time() - start_time
        # 100 次请求应该在 1 秒内完成（因为没有超过限制）
        self.assertLess(elapsed, 1.0)
        print(f"测试通过：100次高频请求耗时: {elapsed:.3f}秒")


if __name__ == '__main__':
    unittest.main()
