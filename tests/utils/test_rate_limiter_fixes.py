# -*- coding: utf-8 -*-
"""
@desc: 限流器修复测试 - 验证外部配置和端口域名解析
@author: 1nchaos
@time: 2026/4/15
@log: 测试限流器的修复功能
"""

import json
import os
import tempfile
import unittest

from adata.common.utils.rate_limiter import (
    RateLimitConfig,
    RateLimitConfigLoader,
    SlidingWindowRateLimiter,
    configure_domain_limit,
)


class TestRateLimitConfigLoader(unittest.TestCase):
    """测试配置加载器"""
    
    def test_load_config_from_json(self):
        """测试从JSON文件加载配置"""
        # 创建临时配置文件
        config_data = {
            "rate_limits": {
                "api.example.com": {
                    "max_requests": 50,
                    "time_window": 30,
                    "wait_timeout": 10.0
                },
                "api2.example.com": [20, 60]  # 列表格式
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            configs = RateLimitConfigLoader.load_config(temp_path)
            
            # 验证配置加载
            self.assertIn("api.example.com", configs)
            self.assertEqual(configs["api.example.com"].max_requests, 50)
            self.assertEqual(configs["api.example.com"].time_window, 30)
            self.assertEqual(configs["api.example.com"].wait_timeout, 10.0)
            
            # 验证列表格式
            self.assertIn("api2.example.com", configs)
            self.assertEqual(configs["api2.example.com"].max_requests, 20)
            self.assertEqual(configs["api2.example.com"].time_window, 60)
        finally:
            os.unlink(temp_path)
    
    def test_save_config_to_json(self):
        """测试保存配置到JSON文件"""
        configs = {
            "test.example.com": RateLimitConfig(max_requests=25, time_window=45)
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            temp_path = f.name
        
        try:
            RateLimitConfigLoader.save_config(configs, temp_path)
            
            # 验证保存的文件
            with open(temp_path, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            self.assertIn("rate_limits", saved_data)
            self.assertIn("test.example.com", saved_data["rate_limits"])
            self.assertEqual(saved_data["rate_limits"]["test.example.com"]["max_requests"], 25)
        finally:
            os.unlink(temp_path)


class TestDomainWithPort(unittest.TestCase):
    """测试带端口域名的解析"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_get_domain_with_port(self):
        """测试提取带端口的域名"""
        test_cases = [
            ("https://api.example.com:8080/data", "api.example.com:8080"),
            ("http://localhost:3000/api", "localhost:3000"),
            ("https://api.example.com/data", "api.example.com"),
            ("api.example.com:9090/path", "api.example.com:9090"),  # 无scheme
        ]
        
        for url, expected in test_cases:
            with self.subTest(url=url):
                result = self.limiter._get_domain(url)
                self.assertEqual(result, expected)
    
    def test_domain_config_with_port(self):
        """测试带端口域名的配置匹配"""
        # 配置带端口的域名
        configure_domain_limit("api.example.com:8080", max_requests=5, time_window=60)
        configure_domain_limit("api.example.com", max_requests=10, time_window=60)
        
        # 带端口的URL应该匹配带端口的配置
        config1 = self.limiter._get_domain_config("api.example.com:8080")
        self.assertEqual(config1.max_requests, 5)
        
        # 不带端口的URL应该匹配不带端口的配置
        config2 = self.limiter._get_domain_config("api.example.com")
        self.assertEqual(config2.max_requests, 10)
    
    def test_domain_config_fallback_to_no_port(self):
        """测试带端口域名回退到不带端口配置"""
        # 只配置不带端口的域名
        configure_domain_limit("api.example.com", max_requests=15, time_window=60)
        
        # 带端口的URL应该回退到不带端口的配置
        config = self.limiter._get_domain_config("api.example.com:8080")
        self.assertEqual(config.max_requests, 15)


class TestWildcardDomainMatching(unittest.TestCase):
    """测试通配符域名匹配"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_wildcard_domain_match(self):
        """测试通配符域名匹配"""
        # 配置通配符域名（使用唯一的测试域名）
        configure_domain_limit("*.wildcard-test.com", max_requests=8, time_window=60)
        
        # 子域名应该匹配
        config1 = self.limiter._get_domain_config("api.wildcard-test.com")
        self.assertEqual(config1.max_requests, 8)
        
        config2 = self.limiter._get_domain_config("www.wildcard-test.com")
        self.assertEqual(config2.max_requests, 8)
        
        # 主域名不应该匹配
        config3 = self.limiter._get_domain_config("wildcard-test.com")
        self.assertEqual(config3.max_requests, 30)  # 默认值


class TestExternalConfigLoading(unittest.TestCase):
    """测试外部配置加载"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_load_config_from_file(self):
        """测试从文件加载配置到限流器"""
        # 创建临时配置文件
        config_data = {
            "rate_limits": {
                "test1.example.com": {"max_requests": 5, "time_window": 30},
                "test2.example.com": {"max_requests": 10, "time_window": 60}
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(config_data, f)
            temp_path = f.name
        
        try:
            # 加载配置
            self.limiter.load_config_file(temp_path)
            
            # 验证配置已加载
            config1 = self.limiter._get_domain_config("test1.example.com")
            self.assertEqual(config1.max_requests, 5)
            self.assertEqual(config1.time_window, 30)
            
            config2 = self.limiter._get_domain_config("test2.example.com")
            self.assertEqual(config2.max_requests, 10)
        finally:
            os.unlink(temp_path)


class TestRateLimiterIntegration(unittest.TestCase):
    """测试限流器集成到请求流程"""
    
    def setUp(self):
        """每个测试用例前重置限流器"""
        self.limiter = SlidingWindowRateLimiter()
        self.limiter.reset()
    
    def test_rate_limiter_acquire_with_empty_url(self):
        """测试空URL的处理"""
        # 空URL应该直接返回True，不限流
        result = self.limiter.acquire("")
        self.assertTrue(result)
    
    def test_rate_limiter_acquire_with_invalid_url(self):
        """测试无效URL的处理"""
        # 无效URL应该返回原始字符串作为域名
        domain = self.limiter._get_domain("not_a_valid_url")
        self.assertEqual(domain, "not_a_valid_url")


if __name__ == '__main__':
    unittest.main()
