"""数据存储工具"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from astrbot.api.star import StarTools
from astrbot.api import logger


class DataStorage:
    """数据存储管理器"""
    
    def __init__(self, plugin_name: str = "papertrading", plugin_config=None):
        """初始化数据存储"""
        self.plugin_name = plugin_name
        self.plugin_config = plugin_config
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self._ensure_data_structure()
    
    def _ensure_data_structure(self):
        """确保数据目录结构存在"""
        # 创建必要的数据文件
        files = {
            'users.json': {},
            'orders.json': {},
            'positions.json': {},
            'market_data_cache.json': {},
            'config.json': {
                # 保留市场时间配置（非插件配置项）
                'market_hours': {
                    'morning': {'start': '09:30', 'end': '11:30'},
                    'afternoon': {'start': '13:00', 'end': '15:00'}
                }
            }
        }
        
        for filename, default_data in files.items():
            file_path = self.data_dir / filename
            if not file_path.exists():
                self._save_json(filename, default_data)
    
    def _get_file_path(self, filename: str) -> Path:
        """获取文件路径"""
        return self.data_dir / filename
    
    def _load_json(self, filename: str) -> Dict[str, Any]:
        """加载JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"加载文件失败 {filename}: {e}")
            return {}
    
    def _save_json(self, filename: str, data: Dict[str, Any]):
        """保存JSON文件"""
        file_path = self._get_file_path(filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存文件失败 {filename}: {e}")
    
    # 用户数据操作
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户数据"""
        users = self._load_json('users.json')
        return users.get(user_id)
    
    def save_user(self, user_id: str, user_data: Dict[str, Any]):
        """保存用户数据"""
        users = self._load_json('users.json')
        users[user_id] = user_data
        self._save_json('users.json', users)
    
    def get_all_users(self) -> Dict[str, Any]:
        """获取所有用户数据"""
        return self._load_json('users.json')
    
    def delete_user(self, user_id: str):
        """删除用户数据"""
        users = self._load_json('users.json')
        if user_id in users:
            del users[user_id]
            self._save_json('users.json', users)
    
    # 订单数据操作
    def get_orders(self, user_id: str = None) -> List[Dict[str, Any]]:
        """获取订单数据"""
        orders = self._load_json('orders.json')
        if user_id:
            return [order for order in orders.values() if order.get('user_id') == user_id]
        return list(orders.values())
    
    def get_next_order_number(self) -> str:
        """获取下一个订单号（五位数字序号）"""
        counter_data = self._load_json('order_counter.json')
        current_number = counter_data.get('current_number', 0)
        
        # 递增订单号
        next_number = current_number + 1
        
        # 如果超过99999，重置为1
        if next_number > 99999:
            next_number = 1
        
        # 保存新的计数器
        counter_data['current_number'] = next_number
        self._save_json('order_counter.json', counter_data)
        
        # 返回五位数字字符串，不足补零
        return f"{next_number:05d}"
    
    def save_order(self, order_id: str, order_data: Dict[str, Any]):
        """保存订单数据"""
        orders = self._load_json('orders.json')
        orders[order_id] = order_data
        self._save_json('orders.json', orders)
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """获取单个订单"""
        orders = self._load_json('orders.json')
        return orders.get(order_id)
    
    def delete_order(self, order_id: str):
        """删除订单"""
        orders = self._load_json('orders.json')
        if order_id in orders:
            del orders[order_id]
            self._save_json('orders.json', orders)
    
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """获取所有待成交订单"""
        orders = self._load_json('orders.json')
        return [order for order in orders.values() if order.get('status') == 'pending']
    
    def get_user_pending_buy_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户待成交的买单（用于计算冻结资金）"""
        orders = self._load_json('orders.json')
        return [order for order in orders.values() 
                if order.get('user_id') == user_id 
                and order.get('status') == 'pending' 
                and order.get('order_type') == 'buy']
    
    def calculate_frozen_funds(self, user_id: str) -> float:
        """计算用户的冻结资金（买入挂单占用的资金）"""
        pending_buy_orders = self.get_user_pending_buy_orders(user_id)
        total_frozen = 0.0
        
        # 导入market_rules来计算买入金额
        try:
            from ..services.market_rules import MarketRulesEngine
            market_rules = MarketRulesEngine(self)
            
            for order in pending_buy_orders:
                order_volume = order.get('order_volume', 0)
                order_price = order.get('order_price', 0)
                if order_volume > 0 and order_price > 0:
                    # 计算包含手续费的总成本
                    total_cost = market_rules.calculate_buy_amount(order_volume, order_price)
                    total_frozen += total_cost
                    
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"计算冻结资金失败: {e}")
            
        return total_frozen
    
    def get_user_order_history(self, user_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """
        获取用户历史订单（分页）
        
        Args:
            user_id: 用户ID
            page: 页码（从1开始）
            page_size: 每页记录数
            
        Returns:
            包含订单列表、总数、分页信息的字典
        """
        orders = self._load_json('orders.json')
        
        # 过滤用户订单，排除待成交状态
        user_orders = [
            order for order in orders.values() 
            if order.get('user_id') == user_id 
            and order.get('status') in ['filled', 'cancelled', 'partial']
        ]
        
        # 按时间倒序排序
        user_orders.sort(key=lambda x: x.get('update_time', 0), reverse=True)
        
        # 计算分页
        total_count = len(user_orders)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        
        # 获取当前页订单
        current_page_orders = user_orders[start_index:end_index]
        
        return {
            'orders': current_page_orders,
            'total_count': total_count,
            'current_page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    
    # 持仓数据操作
    def get_positions(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户持仓"""
        positions = self._load_json('positions.json')
        user_positions = positions.get(user_id, {})
        return list(user_positions.values())
    
    def save_position(self, user_id: str, stock_code: str, position_data: Dict[str, Any]):
        """保存持仓数据"""
        positions = self._load_json('positions.json')
        if user_id not in positions:
            positions[user_id] = {}
        positions[user_id][stock_code] = position_data
        self._save_json('positions.json', positions)
    
    def get_position(self, user_id: str, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取单个持仓"""
        positions = self._load_json('positions.json')
        return positions.get(user_id, {}).get(stock_code)
    
    def delete_position(self, user_id: str, stock_code: str):
        """删除持仓"""
        positions = self._load_json('positions.json')
        if user_id in positions and stock_code in positions[user_id]:
            del positions[user_id][stock_code]
            if not positions[user_id]:  # 如果用户没有任何持仓，删除用户条目
                del positions[user_id]
            self._save_json('positions.json', positions)
    
    # 市场数据缓存操作
    def get_market_cache(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取市场数据缓存"""
        cache = self._load_json('market_data_cache.json')
        return cache.get(stock_code)
    
    def save_market_cache(self, stock_code: str, market_data: Dict[str, Any]):
        """保存市场数据缓存"""
        cache = self._load_json('market_data_cache.json')
        cache[stock_code] = market_data
        self._save_json('market_data_cache.json', cache)
    
    def clear_market_cache(self):
        """清空市场数据缓存"""
        self._save_json('market_data_cache.json', {})
    
    # 配置操作
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._load_json('config.json')
    
    def save_config(self, config: Dict[str, Any]):
        """保存配置"""
        self._save_json('config.json', config)
    
    def reset_user_data(self, user_id: str):
        """重置用户所有数据 (删除用户、持仓、订单)"""
        # 1. 删除用户基础信息
        self.delete_user(user_id)
        
        # 2. 删除持仓
        positions = self._load_json('positions.json')
        if user_id in positions:
            del positions[user_id]
            self._save_json('positions.json', positions)
            
        # 3. 删除订单
        orders = self._load_json('orders.json')
        # 找出该用户的所有订单ID
        keys_to_del = [oid for oid, order in orders.items() if order.get('user_id') == user_id]
        if keys_to_del:
            for k in keys_to_del:
                del orders[k]
            self._save_json('orders.json', orders)

    def get_plugin_config_value(self, key: str, default=None):
        """获取插件配置值（优先从插件配置读取，回退到本地配置）"""
        if self.plugin_config and hasattr(self.plugin_config, 'get'):
            return self.plugin_config.get(key, default)
        else:
            # 回退到本地配置（向后兼容）
            config = self.get_config()
            return config.get(key, default)
