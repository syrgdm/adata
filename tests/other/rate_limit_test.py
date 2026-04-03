# -*- coding: utf-8 -*-
"""
测试频率限制功能
"""
import time
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from adata.common.utils.sunrequests import sun_requests, RateLimiter


def test_rate_limit_basic():
    """
    测试基本频率限制功能
    """
    print("=" * 60)
    print("测试基本频率限制功能")
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
    
    # 恢复默认限制
    RateLimiter.set_default_limit(30)
    print("\n默认限制已恢复为 30 次/分钟")
    print("=" * 60)


def test_rate_limit_with_sun_requests():
    """
    通过 sun_requests 测试频率限制
    """
    print("\n" + "=" * 60)
    print("通过 sun_requests 测试频率限制")
    print("=" * 60)
    
    # 测试设置默认限制
    sun_requests.set_rate_limit(limit=5)
    print(f"\n默认限制已设置为 5 次/分钟")
    
    # 测试设置指定域名限制
    sun_requests.set_rate_limit(domain="example.com", limit=10)
    print("example.com 限制已设置为 10 次/分钟")
    
    # 恢复默认限制
    sun_requests.set_rate_limit(limit=30)
    print("\n默认限制已恢复为 30 次/分钟")
    print("=" * 60)


if __name__ == "__main__":
    test_rate_limit_basic()
    test_rate_limit_with_sun_requests()
    print("\n所有测试完成！")
