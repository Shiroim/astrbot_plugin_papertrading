"""交易服务协调器 - 统一处理交易流程中的公共逻辑"""
import time
from typing import Optional, Dict, Any, Tuple, List
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..models.stock import StockInfo
from ..models.user import User
from ..utils.data_storage import DataStorage
from ..utils.validators import Validators
from ..utils.formatters import Formatters
from .stock_data import StockDataService


class TradeCoordinator:
    """
    交易协调器
    统一处理股票搜索、价格解析、用户验证等公共逻辑
    """
    
    def __init__(self, storage: DataStorage, stock_service: StockDataService, trading_engine=None):
        self.storage = storage
        self.stock_service = stock_service
        self._trading_engine = trading_engine
    
    def get_isolated_user_id(self, event: AstrMessageEvent) -> str:
        """
        获取隔离的用户ID，确保不同群聊中的数据隔离
        格式: platform:sender_id:session_id
        """
        platform_name = event.get_platform_name()
        sender_id = event.get_sender_id()
        session_id = event.get_session_id()
        
        # 修复开启群聊隔离后，session_id 包含 group_id 前缀的问题
        # 兼容性修复：处理 session_id 包含 group_id 前缀的情况 (OneBot v11 Adapter issue)
        # 某些情况下 session_id 会变成 group_id_user_id 格式
        if sender_id and session_id.startswith(f"{sender_id}_"):
            # 去除前缀，还原为纯 user_id
            session_id = session_id[len(sender_id)+1:]
        
        return f"{platform_name}:{sender_id}:{session_id}"
    
    async def validate_user_registration(self, event: AstrMessageEvent) -> Tuple[bool, Optional[str], Optional[User]]:
        """
        验证用户是否已注册
        
        Returns:
            (是否已注册, 错误信息, 用户对象)
        """
        user_id = self.get_isolated_user_id(event)
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            return False, "❌ 您还未注册，请先使用 /股票注册 注册账户", None
        
        user = User.from_dict(user_data)
        return True, None, user
    
    async def search_and_validate_stock(self, keyword: str) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
        """
        搜索并验证股票
        
        Returns:
            (是否找到, 错误信息, 股票信息字典)
        """
        # 先尝试精确匹配（如果是6位数字代码）
        if keyword.isdigit() and len(keyword) == 6:
            stock_code = Validators.normalize_stock_code(keyword)
            if stock_code:
                try:
                    stock_info = await self.stock_service.get_stock_info(stock_code)
                    if stock_info:
                        return True, None, {
                            'code': stock_code,
                            'name': stock_info.name,
                            'market': '未知'
                        }
                except Exception:
                    pass
        
        # 模糊搜索
        try:
            candidates = await self.stock_service.search_stocks_fuzzy(keyword)
            
            if not candidates:
                return False, f"❌ 未找到相关股票: {keyword}\n请尝试使用股票代码或准确的股票名称", None
            
            if len(candidates) == 1:
                return True, None, candidates[0]
            else:
                # 多个候选，需要用户选择
                return True, None, {"multiple": True, "candidates": candidates}
                
        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return False, "❌ 搜索股票时出现错误，请稍后重试", None
    
    async def parse_and_validate_price(self, price_text: str, stock_code: str, stock_name: str) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        解析并验证价格输入（支持涨停/跌停文本）
        
        Returns:
            (解析成功, 错误信息, 解析后价格)
        """
        if not price_text:
            return True, None, None  # 市价单
        
        try:
            # 使用统一的价格服务获取涨跌停价格
            from .price_service import get_price_limit_service
            price_service = get_price_limit_service(self.storage)
            
            # 获取当前涨跌停价格
            price_info = await price_service.get_limit_prices_for_trading(stock_code, stock_name)
            
            if price_info['limit_up'] > 0:
                # 使用价格计算器解析价格文本
                from ..utils.price_calculator import get_price_calculator
                price_calc = get_price_calculator(self.storage)
                
                price = price_calc.parse_price_text(
                    price_text, 
                    price_info['limit_up'], 
                    price_info['limit_down']
                )
                if price is None:
                    return False, f"❌ 无法解析价格参数: {price_text}\n支持格式: 数字价格、涨停、跌停", None
                
                logger.debug(f"价格解析成功: {price_text} -> {price} (策略: {price_info.get('strategy', 'unknown')})")
                return True, None, price
            else:
                # 如果无法获取涨跌停，尝试按数字解析
                try:
                    price = float(price_text)
                    return True, None, price
                except ValueError:
                    return False, f"❌ 无法解析价格参数: {price_text}", None
                    
        except Exception as e:
            logger.error(f"解析价格失败: {e}")
            return False, "❌ 价格解析时出现错误", None
    
    async def get_stock_realtime_info(self, stock_code: str) -> Tuple[bool, Optional[str], Optional[StockInfo]]:
        """
        获取股票实时信息
        
        Returns:
            (获取成功, 错误信息, 股票信息)
        """
        try:
            stock_info = await self.stock_service.get_stock_info(stock_code)
            if not stock_info:
                return False, f"❌ 无法获取股票实时数据", None
            
            return True, None, stock_info
            
        except Exception as e:
            logger.error(f"获取股票信息失败: {e}")
            return False, "❌ 获取股票信息时出现错误", None
    
    def parse_trading_parameters(self, params: List[str], require_price: bool = False) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        解析交易参数
        
        Args:
            params: 参数列表 [股票代码/名称, 数量, 价格(可选)]
            require_price: 是否必须提供价格
            
        Returns:
            (解析成功, 错误信息, 参数字典)
        """
        min_params = 3 if require_price else 2
        
        if len(params) < min_params:
            if require_price:
                return False, "❌ 参数不足\n\n格式: /命令 股票代码/名称 数量 价格\n例: /限价买入 平安银行 1000 12.50\n    /限价买入 平安银行 1000 涨停", None
            else:
                return False, "❌ 参数不足\n\n格式: /命令 股票代码/名称 数量\n例: /买入 平安银行 1000", None
        
        keyword = params[0]
        
        # 解析数量
        try:
            volume = int(params[1])
            if not Validators.is_valid_volume(volume):
                return False, f"❌ 无效的交易数量: {volume}，必须是100的倍数", None
        except (ValueError, IndexError):
            return False, f"❌ 数量格式错误: {params[1]}", None
        
        # 解析价格（如果提供）
        price_text = None
        if len(params) >= 3:
            price_text = params[2]
        elif require_price:
            return False, "❌ 限价单必须提供价格", None
        
        return True, None, {
            'keyword': keyword,
            'volume': volume,
            'price_text': price_text
        }
    
    def format_trading_confirmation(self, stock_name: str, stock_code: str, 
                                  trade_type: str, volume: int, 
                                  price: Optional[float], current_price: float) -> str:
        """
        格式化交易确认信息
        """
        if price:
            display_price = f"{price:.2f}元"
        else:
            display_price = f"{current_price:.2f}元(当前价)"
        
        return (
            f"📋 即将执行交易\n"
            f"股票: {stock_name} ({stock_code})\n"
            f"操作: {trade_type}\n" 
            f"数量: {volume}股\n"
            f"价格: {display_price}"
        )
    
    def format_stock_candidates(self, candidates: List[Dict[str, str]]) -> str:
        """
        格式化股票候选列表
        """
        text = f"🔍 找到多个相关股票，请选择:\n\n"
        for i, candidate in enumerate(candidates[:5], 1):  # 最多显示5个
            text += f"{i}. {candidate['name']} ({candidate['code']}) [{candidate['market']}]\n"
        text += f'\n💡 请回复数字 1-{len(candidates[:5])} 选择股票，或输入"取消"退出'
        return text
    
    def set_trading_engine(self, trading_engine) -> None:
        """延迟注入 TradingEngine（解决循环依赖时的初始化顺序问题）"""
        self._trading_engine = trading_engine

    async def update_user_assets_if_needed(self, user_id: str):
        """更新用户总资产（如果需要）"""
        try:
            if self._trading_engine is None:
                from .trading_engine import TradingEngine
                self._trading_engine = TradingEngine(self.storage, self.stock_service)
            await self._trading_engine.update_user_assets(user_id)
        except Exception as e:
            logger.error(f"更新用户资产失败: {e}")
    
    def validate_trading_amount(self, volume: int, price: float, min_amount: float = 100.0) -> Tuple[bool, str]:
        """
        验证交易金额是否满足最小要求
        
        Returns:
            (是否有效, 错误信息)
        """
        total_amount = volume * price
        if total_amount < min_amount:
            return False, f"❌ 单笔交易金额不能少于{min_amount:.0f}元，当前: {total_amount:.2f}元"
        
        return True, ""
    
    def format_error_message(self, operation: str, error: str) -> str:
        """
        格式化错误消息
        """
        return f"❌ {operation}失败: {error}"
    
    def format_success_message(self, operation: str, message: str) -> str:
        """
        格式化成功消息
        """
        return f"✅ {operation}成功: {message}"
