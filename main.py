"""A股模拟交易插件
完整的模拟股票交易系统，支持买卖、挂单、持仓管理等功能
"""
import asyncio
from datetime import datetime, time as dt_time, timedelta
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.core.star.filter.permission import PermissionType

# 导入重构后的处理器
from .handlers.trading_handlers import TradingCommandHandlers
from .handlers.query_handlers import QueryCommandHandlers
from .handlers.user_handlers import UserCommandHandlers

# 导入服务层
from .services.trade_coordinator import TradeCoordinator
from .services.user_interaction import UserInteractionService
from .services.stock_data import StockDataService
from .services.trading_engine import TradingEngine
from .services.order_monitor import OrderMonitorService
from .services.market_rules import MarketRulesEngine
from .utils.data_storage import DataStorage


class PaperTradingPlugin(Star):
    """
    A股模拟交易插件
    
    功能特点：
    - 🎯 完整的模拟交易体验：买入、卖出、挂单、撤单
    - 📊 实时股价查询和持仓管理  
    - 🏆 群内排行榜功能
    - ⚡ 基于真实股票数据的现价交易
    - 🛡️ 完整的A股交易规则支持（T+1、涨跌停等）
    - 🤝 真正的用户交互等待机制
    """
    
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.plugin_config = config  # 保存插件配置
        self.astrbot_config: AstrBotConfig = context.get_config()  # AstrBot全局配置
        
        # 初始化服务层（依赖注入模式）
        self._initialize_services()
        
        # 初始化命令处理器
        self._initialize_handlers()
        
        logger.info("A股模拟交易插件初始化完成")
    
    def _initialize_services(self):
        """初始化服务层"""
        # 数据存储服务 - 传递插件配置
        self.storage = DataStorage("papertrading", self.plugin_config)
        
        # 股票数据服务
        self.stock_service = StockDataService(self.storage)
        
        # 交易引擎（依赖注入）
        self.trading_engine = TradingEngine(self.storage, self.stock_service)
        
        # 交易协调器服务
        self.trade_coordinator = TradeCoordinator(self.storage, self.stock_service)
        
        # 用户交互服务
        self.user_interaction = UserInteractionService()
        
        # 挂单监控服务（修复参数不匹配问题）
        self.order_monitor = OrderMonitorService(self.storage, self.stock_service)
    
    def _initialize_handlers(self):
        """初始化命令处理器"""
        # 交易命令处理器（注入TradingEngine）
        self.trading_handlers = TradingCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction,
            self.trading_engine
        )
        
        # 查询命令处理器
        self.query_handlers = QueryCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction,
            self.order_monitor
        )
        
        # 用户管理处理器
        self.user_handlers = UserCommandHandlers(
            self.trade_coordinator, 
            self.user_interaction, 
            self.storage  # 传递storage而不是config
        )
    
    async def initialize(self):
        """插件初始化（AstrBot生命周期方法）"""
        try:
            # 启动挂单监控服务
            monitor_interval = self.storage.get_plugin_config_value("monitor_interval", 15)
            if monitor_interval > 0:
                await self.order_monitor.start_monitoring()
                logger.info(f"挂单监控服务已启动，轮询间隔: {monitor_interval}秒")
            else:
                logger.info("轮询间隔为0，挂单监控服务暂停")
            
            # 注册定时任务
            asyncio.create_task(self._daily_maintenance_task())
            
            logger.info("A股模拟交易插件启动完成")
        except Exception as e:
            logger.error(f"插件初始化失败: {e}")
    
    async def terminate(self):
        """插件销毁（AstrBot生命周期方法）"""
        try:
            # 停止挂单监控
            await self.order_monitor.stop_monitoring()
            logger.info("A股模拟交易插件已停止")
        except Exception as e:
            logger.error(f"插件停止时出错: {e}")
    
    async def _daily_maintenance_task(self):
        """每日维护任务"""        
        while True:
            try:
                # 每天凌晨2点执行维护
                now = datetime.now()
                target_time = datetime.combine(now.date(), dt_time(2, 0))
                
                if now > target_time:
                    # 修复日期计算错误：使用timedelta避免跨月问题
                    target_time = target_time + timedelta(days=1)
                
                sleep_seconds = (target_time - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
                # 执行维护任务
                await self._perform_daily_maintenance()
                
            except Exception as e:
                logger.error(f"每日维护任务错误: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时
    
    async def _perform_daily_maintenance(self):
        """执行每日维护"""
        logger.info("开始执行每日维护任务")
        
        try:
            # 更新所有用户的T+1持仓状态
            all_users = self.storage.get_all_users()
            for user_id in all_users:
                try:
                    # 使用已初始化的服务实例，避免局部导入
                    market_rules = MarketRulesEngine(self.storage)
                    market_rules.make_positions_available_for_next_day(user_id)
                    
                    # 更新用户总资产（使用已有的trading_engine实例）
                    await self.trading_engine.update_user_assets(user_id)
                except Exception as e:
                    logger.error(f"更新用户 {user_id} 数据失败: {e}")
            
            # 清理过期的市场数据缓存
            self.storage.clear_market_cache()
            
            logger.info("每日维护任务完成")
        except Exception as e:
            logger.error(f"每日维护任务执行失败: {e}")

    # ==================== 用户管理命令 ====================
    
    @filter.command("股票注册")
    async def register_user(self, event: AstrMessageEvent):
        """用户注册"""
        async for result in self.user_handlers.handle_user_registration(event):
            yield result

    @filter.command("股票入金")
    async def deposit_money(self, event: AstrMessageEvent):
        """股票入金"""
        async for result in self.user_handlers.handle_deposit(event):
            yield result

    @filter.command("股票出金")
    async def withdraw_money(self, event: AstrMessageEvent):
        """股票出金"""
        async for result in self.user_handlers.handle_withdraw(event):
            yield result

    @filter.command("股票重置")
    async def reset_account(self, event: AstrMessageEvent):
        """股票重置"""
        async for result in self.user_handlers.handle_reset(event):
            yield result

    # ==================== 交易命令 ====================
    
    @filter.command("买入")
    async def market_buy_stock(self, event: AstrMessageEvent):
        """市价买入股票"""
        async for result in self.trading_handlers.handle_market_buy(event):
            yield result
    
    @filter.command("限价买入")
    async def limit_buy_stock(self, event: AstrMessageEvent):
        """限价买入股票"""
        async for result in self.trading_handlers.handle_limit_buy(event):
            yield result
    
    @filter.command("卖出")
    async def market_sell_stock(self, event: AstrMessageEvent):
        """市价卖出股票"""
        async for result in self.trading_handlers.handle_market_sell(event):
            yield result
    
    @filter.command("限价卖出")
    async def limit_sell_stock(self, event: AstrMessageEvent):
        """限价卖出股票"""
        async for result in self.trading_handlers.handle_limit_sell(event):
            yield result
    
    @filter.command("股票撤单")
    async def cancel_order(self, event: AstrMessageEvent):
        """撤销订单"""
        async for result in self.trading_handlers.handle_cancel_order(event):
            yield result

    # ==================== 查询命令 ====================
    
    @filter.command("股票账户")
    async def show_account_info(self, event: AstrMessageEvent):
        """显示账户信息"""
        async for result in self.query_handlers.handle_account_info(event):
            yield result
    
    @filter.command("股价")
    async def show_stock_price(self, event: AstrMessageEvent):
        """查询股价"""
        async for result in self.query_handlers.handle_stock_price(event):
            yield result
    
    @filter.command("股票排行")
    async def show_ranking(self, event: AstrMessageEvent):
        """显示群内排行榜"""
        async for result in self.query_handlers.handle_ranking(event):
            yield result
    
    @filter.command("历史订单")
    async def show_order_history(self, event: AstrMessageEvent):
        """显示历史订单"""
        async for result in self.query_handlers.handle_order_history(event):
            yield result
    
    @filter.command("股票帮助")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        async for result in self.query_handlers.handle_help(event):
            yield result
    
    # ==================== 管理员命令 ====================
    
    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("轮询状态")
    async def show_polling_status(self, event: AstrMessageEvent):
        """显示轮询监控状态（管理员专用）"""
        async for result in self.query_handlers.handle_polling_status(event):
            yield result