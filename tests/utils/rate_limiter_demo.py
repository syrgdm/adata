# -*- coding: utf-8 -*-
"""
@desc: 限流器使用示例
@author: 1nchaos
@time: 2026/4/15
@log: 演示限流器的各种使用方式
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from adata.common.utils import (
    rate_limiter,
    rate_limit_by_domain,
    configure_domain_limit,
    RateLimitConfig,
)
from adata.common.utils import requests


def demo1_basic_usage():
    """示例1：基础用法 - 直接使用限流器"""
    print("=" * 60)
    print("示例1：基础用法 - 直接使用限流器")
    print("=" * 60)
    
    # 配置特定域名的限流规则：每分钟最多5次请求
    configure_domain_limit("api.example.com", max_requests=5, time_window=60)
    
    url = "https://api.example.com/data"
    
    # 尝试获取请求许可（非阻塞模式）
    for i in range(7):
        can_request = rate_limiter.try_acquire(url)
        if can_request:
            print(f"  第{i+1}次请求：[OK] 获取许可成功")
        else:
            print(f"  第{i+1}次请求：[X] 被限流，请稍后再试")
    
    print(f"  当前请求计数: {rate_limiter.get_current_count(url)}")
    print(f"  剩余额度: {rate_limiter.get_remaining_quota(url)}")
    print()


def demo2_decorator_usage():
    """示例2：使用装饰器模式 - 低侵入接入"""
    print("=" * 60)
    print("示例2：使用装饰器模式 - 低侵入接入")
    print("=" * 60)
    
    # 方式1：自动提取第一个参数作为URL
    @rate_limit_by_domain(max_requests=3, time_window=10)
    def fetch_data_auto(url, params=None):
        """自动从第一个参数提取URL进行限流"""
        print(f"  执行请求: {url}")
        # 实际项目中这里调用 requests.get(url, params=params)
        return {"status": "success", "url": url}
    
    # 方式2：自定义URL提取函数
    @rate_limit_by_domain(
        max_requests=3,
        time_window=10,
        url_extractor=lambda api_url, **kwargs: api_url
    )
    def fetch_data_custom(api_url=None, headers=None, timeout=30):
        """通过url_extractor自定义提取URL"""
        print(f"  执行请求: {api_url}")
        return {"status": "success", "url": api_url}
    
    # 测试自动提取模式
    print("  测试自动提取URL模式（限流：3次/10秒）：")
    for i in range(5):
        result = fetch_data_auto(f"https://auto.example.com/api/{i}")
        print(f"    结果: {result}")
    
    print()
    print("  测试自定义URL提取模式（限流：3次/10秒）：")
    for i in range(5):
        result = fetch_data_custom(api_url=f"https://custom.example.com/api/{i}")
        print(f"    结果: {result}")
    print()


def demo3_multi_domain():
    """示例3：多域名独立限流"""
    print("=" * 60)
    print("示例3：多域名独立限流")
    print("=" * 60)
    
    # 为不同域名配置不同的限流规则
    configure_domain_limit("api1.example.com", max_requests=2, time_window=10)
    configure_domain_limit("api2.example.com", max_requests=5, time_window=10)
    
    @rate_limit_by_domain(
        url_extractor=lambda domain, **kwargs: f"https://{domain}/data"
    )
    def call_api(domain):
        print(f"  调用 {domain}")
        return f"response from {domain}"
    
    print("  api1.example.com 限流：2次/10秒")
    for i in range(4):
        result = call_api("api1.example.com")
        print(f"    第{i+1}次: {result}")
    
    print()
    print("  api2.example.com 限流：5次/10秒")
    for i in range(7):
        result = call_api("api2.example.com")
        print(f"    第{i+1}次: {result}")
    print()


def demo4_blocking_mode():
    """示例4：阻塞等待模式"""
    print("=" * 60)
    print("示例4：阻塞等待模式（自动排队等待）")
    print("=" * 60)
    
    # 配置限流：每秒2次
    configure_domain_limit("blocking.example.com", max_requests=2, time_window=1)
    
    @rate_limit_by_domain(
        max_requests=2,
        time_window=1,
        url_extractor=lambda idx, **kwargs: "https://blocking.example.com/api"
    )
    def blocking_request(idx):
        print(f"  [{time.strftime('%H:%M:%S')}] 请求 {idx} 开始执行")
        return f"response {idx}"
    
    print("  限流规则：2次/秒，共发送5次请求")
    print("  预期：前2次立即执行，后3次需要等待")
    
    start = time.time()
    for i in range(5):
        blocking_request(i)
    elapsed = time.time() - start
    
    print(f"  总耗时: {elapsed:.2f}秒 (预期 >= 1.5秒)")
    print()


def demo5_concurrent_scenario():
    """示例5：并发场景下的限流"""
    print("=" * 60)
    print("示例5：并发场景下的限流")
    print("=" * 60)
    
    # 重置限流器状态
    rate_limiter.reset()
    
    # 配置限流：每秒3次
    configure_domain_limit("concurrent.example.com", max_requests=3, time_window=1)
    
    @rate_limit_by_domain(
        max_requests=3,
        time_window=1,
        url_extractor=lambda task_id, **kwargs: "https://concurrent.example.com/api"
    )
    def concurrent_task(task_id):
        print(f"  [{time.strftime('%H:%M:%S')}] 任务 {task_id} 执行")
        return f"task {task_id} done"
    
    print("  使用10个线程并发执行10个任务，限流：3次/秒")
    
    start = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(concurrent_task, i) for i in range(10)]
        results = [f.result() for f in as_completed(futures)]
    elapsed = time.time() - start
    
    print(f"  所有任务完成，总耗时: {elapsed:.2f}秒 (预期 >= 3秒)")
    print()


def demo6_real_world_stock_api():
    """示例6：实际场景 - 股票数据API限流"""
    print("=" * 60)
    print("示例6：实际场景 - 股票数据API限流")
    print("=" * 60)
    
    # 重置限流器状态
    rate_limiter.reset()
    
    # 为东方财富接口配置限流：每分钟20次
    configure_domain_limit("push2.eastmoney.com", max_requests=20, time_window=60)
    
    # 为百度接口配置限流：每分钟30次
    configure_domain_limit("finance.pae.baidu.com", max_requests=30, time_window=60)
    
    @rate_limit_by_domain(
        url_extractor=lambda stock_code, source, **kwargs: {
            "eastmoney": f"https://push2.eastmoney.com/api/qt/stock/kline/get?secid=0.{stock_code}",
            "baidu": f"https://finance.pae.baidu.com/api/stock?code={stock_code}",
        }.get(source, "https://default.example.com")
    )
    def fetch_stock_data(stock_code, source="eastmoney"):
        """
        获取股票数据
        
        Args:
            stock_code: 股票代码
            source: 数据源，eastmoney或baidu
        """
        url = {
            "eastmoney": f"https://push2.eastmoney.com/api/qt/stock/kline/get?secid=0.{stock_code}",
            "baidu": f"https://finance.pae.baidu.com/api/stock?code={stock_code}",
        }.get(source, "https://default.example.com")
        
        print(f"  获取股票 {stock_code} 数据 from {source}")
        # 实际项目中：return requests.get(url).json()
        return {"code": stock_code, "source": source, "price": 10.5}
    
    print("  模拟批量获取股票数据（东方财富接口：20次/分钟）")
    stock_codes = ["000001", "000002", "000333", "000858", "002415"]
    
    for code in stock_codes:
        data = fetch_stock_data(code, source="eastmoney")
        print(f"    结果: {data}")
    
    print()
    print("  当前限流状态：")
    print(f"    东方财富: {rate_limiter.get_current_count('https://push2.eastmoney.com/')} / 20")
    print(f"    百度: {rate_limiter.get_current_count('https://finance.pae.baidu.com/')} / 30")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("限流器使用示例演示")
    print("=" * 60 + "\n")
    
    demo1_basic_usage()
    demo2_decorator_usage()
    demo3_multi_domain()
    demo4_blocking_mode()
    demo5_concurrent_scenario()
    demo6_real_world_stock_api()
    
    print("=" * 60)
    print("所有示例演示完成！")
    print("=" * 60)
