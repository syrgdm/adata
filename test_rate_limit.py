# -*- coding: utf-8 -*-
"""
测试频率限制功能
"""
import time
from adata.common.utils.sunrequests import sun_requests


def test_rate_limit():
    """
    测试频率限制功能
    """
    print("开始测试频率限制...")
    
    # 测试设置默认限制
    sun_requests.set_rate_limit(limit=5)
    print(f"默认限制已设置为 5 次/分钟")
    
    # 测试设置指定域名限制
    sun_requests.set_rate_limit(domain="example.com", limit=10)
    print("example.com 限制已设置为 10 次/分钟")
    
    # 快速发送请求测试
    test_url = "https://www.example.com"
    print(f"\n开始对 {test_url} 发送请求...")
    
    start_time = time.time()
    
    # 发送 7 次请求
    for i in range(7):
        print(f"发送第 {i+1} 次请求...")
        # 这里我们不实际发送请求，只测试频率限制逻辑
        # 直接调用 rate_limiter 的 check_and_wait 方法
        sun_requests.rate_limiter.check_and_wait(test_url)
    
    end_time = time.time()
    print(f"\n测试完成，总耗时: {end_time - start_time:.2f} 秒")
    
    # 恢复默认限制
    sun_requests.set_rate_limit(limit=30)
    print("\n默认限制已恢复为 30 次/分钟")


if __name__ == "__main__":
    test_rate_limit()
