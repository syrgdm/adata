# -*- coding: utf-8 -*-
"""
@desc: 限流配置管理器 - 支持从配置文件加载限流规则
@author: 1nchaos
@time: 2026/4/15
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .rate_limiter import rate_limiter


class RateLimitConfig:
    """
    限流配置管理器
    支持多种配置格式：JSON、TOML、INI
    """

    _config_loaded = False

    @classmethod
    def load_config(cls, config_path: Optional[str] = None):
        """
        从配置文件加载限流规则
        :param config_path: 配置文件路径，默认为项目根目录 config.toml / config.json
        """
        if cls._config_loaded:
            return

        if config_path:
            paths = [config_path]
        else:
            project_root = Path(__file__).parent.parent.parent.parent
            paths = [
                project_root / 'config.json',
                project_root / 'config.toml',
                project_root / 'rate_limit.json',
            ]

        for path in paths:
            if os.path.exists(path):
                cls._load_from_file(str(path))
                cls._config_loaded = True
                return

        cls._set_default_config()
        cls._config_loaded = True

    @classmethod
    def _load_from_file(cls, file_path: str):
        """从配置文件加载"""
        if file_path.endswith('.json'):
            cls._load_from_json(file_path)
        elif file_path.endswith('.toml'):
            cls._try_load_from_toml(file_path)

    @classmethod
    def _load_from_json(cls, file_path: str):
        """从JSON配置文件加载"""
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        rate_limit_config = config.get('rate_limit', {})
        if not rate_limit_config:
            cls._set_default_config()
            return

        default = rate_limit_config.get('default', {})
        if default:
            rate_limiter.default_limit = default.get('limit', 30)
            rate_limiter.default_window = default.get('window', 60)

        domains: Dict = rate_limit_config.get('domains', {})
        for domain, rules in domains.items():
            limit = rules.get('limit', 30)
            window = rules.get('window', 60)
            rate_limiter.set_domain_limit(domain, limit, window)

    @classmethod
    def _try_load_from_toml(cls, file_path: str):
        """尝试从TOML文件加载"""
        try:
            import tomllib
            with open(file_path, 'rb') as f:
                config = tomllib.load(f)

            rate_limit_config = config.get('rate_limit', {})
            if not rate_limit_config:
                cls._set_default_config()
                return

            default = rate_limit_config.get('default', {})
            if default:
                rate_limiter.default_limit = default.get('limit', 30)
                rate_limiter.default_window = default.get('window', 60)

            domains: Dict = rate_limit_config.get('domains', {})
            for domain, rules in domains.items():
                limit = rules.get('limit', 30)
                window = rules.get('window', 60)
                rate_limiter.set_domain_limit(domain, limit, window)
        except ImportError:
            cls._set_default_config()

    @classmethod
    def _set_default_config(cls):
        """设置默认配置"""
        rate_limiter.default_limit = 30
        rate_limiter.default_window = 60

        common_domains = [
            ('push2.eastmoney.com', 60, 60),
            ('finance.pae.baidu.com', 45, 60),
            ('push2his.eastmoney.com', 60, 60),
            ('stock.xueqiu.com', 20, 60),
            ('api.money.126.net', 30, 60),
            ('qt.gtimg.cn', 50, 60),
            ('vip.stock.finance.sina.com.cn', 30, 60),
        ]
        for domain, limit, window in common_domains:
            rate_limiter.set_domain_limit(domain, limit, window)

    @classmethod
    def reload_config(cls, config_path: Optional[str] = None):
        """重新加载配置"""
        cls._config_loaded = False
        cls.load_config(config_path)

    @staticmethod
    def get_current_config() -> Dict:
        """获取当前生效的限流配置"""
        config = {
            'default': {
                'limit': rate_limiter.default_limit,
                'window': rate_limiter.default_window
            },
            'domains': {}
        }
        for domain in rate_limiter._domain_configs.keys():
            limit, window = rate_limiter.get_domain_config(domain)
            config['domains'][domain] = {
                'limit': limit,
                'window': window
            }
        return config
