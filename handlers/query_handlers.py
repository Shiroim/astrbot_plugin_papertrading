"""查询命令处理器 - 处理所有查询相关命令"""
import asyncio
from typing import AsyncGenerator, List, Dict, Any
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..models.user import User
from ..models.position import Position
from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..utils.formatters import Formatters
from ..utils.validators import Validators


class QueryCommandHandlers:
    """查询命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, order_monitor=None):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.order_monitor = order_monitor
    
    async def handle_account_info(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示账户信息（合并持仓、余额、订单查询）"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        storage = self.trade_coordinator.storage

        user_data = storage.get_user(user_id)
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return

        try:
            user = User.from_dict(user_data)
            positions = storage.get_positions(user_id)

            # 拉取最新股价并更新持仓市值
            total_market_value = 0.0
            for pos_data in positions:
                if pos_data.get('total_volume', 0) > 0:
                    stock_info = await self.trade_coordinator.stock_service.get_stock_info(pos_data['stock_code'])
                    if stock_info:
                        position = Position.from_dict(pos_data)
                        position.update_market_data(stock_info.current_price)
                        storage.save_position(user_id, position.stock_code, position.to_dict())
                        pos_data.update(position.to_dict())
                        total_market_value += position.market_value
                    else:
                        total_market_value += pos_data.get('market_value', 0)
                else:
                    total_market_value += pos_data.get('market_value', 0)

            # 统一计算总资产（拉取完最新价格后一次性更新）
            frozen_funds = storage.calculate_frozen_funds(user_id)
            total_assets = user.balance + total_market_value + frozen_funds
            user.update_total_assets(total_assets)
            storage.save_user(user_id, user.to_dict())

            info_text = Formatters.format_user_info(user.to_dict(), positions, frozen_funds)

            pending_orders = [o for o in storage.get_orders(user_id) if o.get('status') == 'pending']
            if pending_orders:
                info_text += "\n\n" + Formatters.format_pending_orders(pending_orders)

            yield MessageEventResult().message(info_text)

        except Exception as e:
            logger.error(f"查询账户信息失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_stock_price(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """查询股价（支持模糊搜索）"""
        params = event.message_str.strip().split()[1:]
        
        if not params:
            yield MessageEventResult().message("❌ 请提供股票代码或名称\n格式: /股价 股票代码/名称\n例: /股价 000001 或 /股价 平安银行")
            return
        
        keyword = params[0]
        
        try:
            # 搜索股票
            success, error_msg, result = await self.trade_coordinator.search_and_validate_stock(keyword)
            if not success:
                yield MessageEventResult().message(error_msg)
                return
            
            # 处理多个候选的情况
            if result.get("multiple"):
                candidates = result["candidates"]
                selected_stock, error_msg = await self.user_interaction.wait_for_stock_selection(
                    event, candidates, "股价查询"
                )
                if error_msg:
                    yield MessageEventResult().message(error_msg)
                    return
                if not selected_stock:
                    yield MessageEventResult().message("💭 查询已取消")
                    return
                
                # 查询选中股票的价格
                stock_code = selected_stock['code']
                stock_info = await self.trade_coordinator.stock_service.get_stock_info(stock_code)
                if stock_info:
                    info_text = Formatters.format_stock_info(stock_info.to_dict())
                    yield MessageEventResult().message(info_text)
                else:
                    yield MessageEventResult().message("❌ 无法获取股票信息")
                return
            else:
                # 单个结果，直接查询
                stock_code = result['code']
                stock_info = await self.trade_coordinator.stock_service.get_stock_info(stock_code)
                if stock_info:
                    info_text = Formatters.format_stock_info(stock_info.to_dict())
                    yield MessageEventResult().message(info_text)
                else:
                    yield MessageEventResult().message("❌ 无法获取股票信息")
                    
        except Exception as e:
            logger.error(f"查询股价失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_ranking(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示群内排行榜（使用批量拉取确保持仓市值实时）"""
        try:
            platform_name = event.get_platform_name()
            session_id = event.get_session_id()
            session_prefix = f"{platform_name}:"
            session_suffix = f":{session_id}"

            storage = self.trade_coordinator.storage
            all_users_data = storage.get_all_users()

            same_session_users = [
                uid for uid, _ in all_users_data.items()
                if uid.startswith(session_prefix) and uid.endswith(session_suffix)
            ]

            if not same_session_users:
                yield MessageEventResult().message("📊 当前群聊暂无用户排行数据\n请先使用 /股票注册 注册账户")
                return

            # 1) 收集所有用户持仓涉及的股票代码（去重）
            all_stock_codes: set[str] = set()
            user_positions_map: dict[str, list] = {}
            for user_id in same_session_users:
                positions = storage.get_positions(user_id)
                user_positions_map[user_id] = positions
                for pos in positions:
                    if pos.get('total_volume', 0) > 0:
                        all_stock_codes.add(pos['stock_code'])

            # 2) 批量拉取最新股价（复用 30s 缓存，避免 N+1 请求）
            latest_prices: dict[str, float] = {}
            if all_stock_codes:
                stock_info_map = await self.trade_coordinator.stock_service.batch_get_stocks(list(all_stock_codes))
                for code, info in stock_info_map.items():
                    if info:
                        latest_prices[code] = info.current_price

            # 3) 用最新价格更新每个用户的持仓市值并计算总资产
            users_list = []
            for user_id in same_session_users:
                user_data = storage.get_user(user_id)
                if not user_data:
                    continue
                user = User.from_dict(user_data)

                total_market_value = 0.0
                for pos_data in user_positions_map[user_id]:
                    if pos_data.get('total_volume', 0) > 0:
                        price = latest_prices.get(pos_data['stock_code'])
                        if price is not None:
                            position = Position.from_dict(pos_data)
                            position.update_market_data(price)
                            storage.save_position(user_id, position.stock_code, position.to_dict())
                            total_market_value += position.market_value
                        else:
                            total_market_value += pos_data.get('market_value', 0)
                    else:
                        total_market_value += pos_data.get('market_value', 0)

                frozen_funds = storage.calculate_frozen_funds(user_id)
                total_assets = user.balance + total_market_value + frozen_funds
                user.update_total_assets(total_assets)
                storage.save_user(user_id, user.to_dict())
                users_list.append(user.to_dict())

            current_user_id = self.trade_coordinator.get_isolated_user_id(event)

            if not users_list:
                yield MessageEventResult().message("📊 当前群聊暂无用户排行数据\n请先使用 /股票注册 注册账户")
                return

            initial_balance = storage.get_plugin_config_value('initial_balance', 1000000)
            ranking_text = Formatters.format_ranking(users_list, current_user_id, initial_balance)
            yield MessageEventResult().message(ranking_text)

        except Exception as e:
            logger.error(f"查询排行榜失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_order_history(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示历史订单"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        
        # 检查用户是否注册
        if not self.trade_coordinator.storage.get_user(user_id):
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册 注册账户")
            return
        
        # 解析页码参数
        params = event.message_str.strip().split()[1:]
        page = 1
        if params:
            try:
                page = int(params[0])
                if page < 1:
                    page = 1
            except ValueError:
                yield MessageEventResult().message("❌ 页码格式错误\n\n格式: /历史订单 [页码]\n例: /历史订单 1")
                return
        
        try:
            # 获取历史订单
            history_data = self.trade_coordinator.storage.get_user_order_history(user_id, page)
            
            # 格式化输出
            history_text = Formatters.format_order_history(history_data)
            yield MessageEventResult().message(history_text)
            
        except Exception as e:
            logger.error(f"查询历史订单失败: {e}")
            yield MessageEventResult().message("❌ 查询失败，请稍后重试")
    
    async def handle_help(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示帮助信息"""
        help_text = Formatters.format_help_message()
        yield MessageEventResult().message(help_text)
    
    async def handle_polling_status(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """显示轮询监控状态（管理员专用）"""
        if not self.order_monitor:
            yield MessageEventResult().message("❌ 轮询监控服务未初始化")
            return
        
        try:
            status = self.order_monitor.get_monitor_status()
            
            # 构建状态信息
            status_text = "📊 挂单轮询监控状态\n\n"
            
            # 运行状态
            if status['is_running']:
                if status['is_paused']:
                    status_text += "⏸️ 状态: 已暂停（间隔为0）\n"
                else:
                    status_text += "✅ 状态: 正在运行\n"
            else:
                status_text += "❌ 状态: 已停止\n"
            
            # 轮询配置
            status_text += f"⏱️ 轮询间隔: {status['current_interval']}秒\n"
            
            # 上次轮询时间
            status_text += f"🕒 上次轮询: {status['last_poll_time']}\n"
            
            # 下次轮询时间
            status_text += f"🕓 下次轮询: {status['next_poll_time']}\n"
            
            # 连通性状态
            connectivity_icon = "🟢" if status['last_connectivity_status'] else "🔴"
            status_text += f"{connectivity_icon} 连通性: {'正常' if status['last_connectivity_status'] else '异常'}\n"
            status_text += f"📈 连通成功率: {status['connectivity_rate']:.1f}% ({status['connectivity_stats']})\n"
            
            # 交易时间状态
            trading_icon = "🟢" if status['is_trading_time'] else "⭕"
            status_text += f"{trading_icon} 交易时间: {'是' if status['is_trading_time'] else '否'}"
            
            yield MessageEventResult().message(status_text)
            
        except Exception as e:
            logger.error(f"获取轮询状态失败: {e}")
            yield MessageEventResult().message("❌ 获取轮询状态失败，请稍后重试")
