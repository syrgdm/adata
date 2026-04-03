# -*- coding: utf-8 -*-
"""
简单测试频率限制功能
"""
import time
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from adata.common.utils.sunrequests import RateLimiter


def test_rate_limiter():
    """
    测试 RateLimiter 功能
    """
    print("开始测试 RateLimiter...")
    
    # 获取单例实例
    limiter = RateLimiter()
    
    # 测试设置默认限制
    limiter.set_default_limit(5)
    print(f"默认限制已设置为 5 次/分钟")
    
    # 测试设置指定域名限制
    limiter.set_domain_limit("example.com", 10)
    print("example.com 限制已设置为 10 次/分钟")
    
    # 测试获取限制
    print(f"example.com 的限制: {limiter.get_domain_limit('example.com')}")
    print(f"other.com 的限制: {limiter.get_domain_limit('other.com')}")
    
    # 快速发送请求测试
    test_url = "https://www.example.com"
    print(f"\n开始对 {test_url} 发送请求...")
    
    start_time = time.time()
    
    # 发送 7 次请求
    for i in range(7):
        print(f"发送第 {i+1} 次请求...")
        limiter.check_and_wait(test_url)
    
    end_time = time.time()
    print(f"\n测试完成，总耗时: {end_time - start_time:.2f} 秒")
    
    # 恢复默认限制
    limiter.set_default_limit(30)
    print("\n默认限制已恢复为 30 次/分钟")


if __name__ == "__main__":
    test_rate_limiter()
