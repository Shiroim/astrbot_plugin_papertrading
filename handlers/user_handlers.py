"""用户管理处理器 - 处理用户注册等相关命令"""
import time
from typing import AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult

from ..services.trade_coordinator import TradeCoordinator
from ..services.user_interaction import UserInteractionService
from ..models.user import User
from ..utils.formatters import Formatters


class UserCommandHandlers:
    """用户命令处理器集合"""
    
    def __init__(self, trade_coordinator: TradeCoordinator, user_interaction: UserInteractionService, storage):
        self.trade_coordinator = trade_coordinator
        self.user_interaction = user_interaction
        self.storage = storage
    
    async def handle_user_registration(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """用户注册"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        user_name = event.get_sender_name() or f"用户{user_id}"
        
        # 检查是否已注册
        existing_user = self.trade_coordinator.storage.get_user(user_id)
        if existing_user:
            yield MessageEventResult().message("您已经注册过了！使用 /股票账户 查看账户信息")
            return
        
        try:
            # 创建新用户，从插件配置获取初始资金
            initial_balance = self.storage.get_plugin_config_value('initial_balance', 1000000)
            
            user = User(
                user_id=user_id,
                username=user_name,
                balance=initial_balance,
                total_assets=initial_balance,
                register_time=int(time.time()),
                last_login=int(time.time())
            )
            
            # 保存用户
            self.trade_coordinator.storage.save_user(user_id, user.to_dict())
            
            yield MessageEventResult().message(
                f"🎉 注册成功！\n"
                f"👤 用户名: {user_name}\n"
                f"💰 初始资金: {Formatters.format_currency(initial_balance)}元\n\n"
                f"📖 输入 /股票帮助 查看使用说明"
            )
            
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            yield MessageEventResult().message("❌ 注册失败，请稍后重试")

    async def handle_deposit(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """股票入金"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册")
            return

        # 解析金额
        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield MessageEventResult().message("❌ 参数错误，格式: /股票入金 <金额>")
            return
            
        try:
            amount = float(parts[1])
            if amount <= 0:
                yield MessageEventResult().message("❌ 金额必须大于0")
                return
        except ValueError:
            yield MessageEventResult().message("❌ 金额格式错误")
            return
            
        # 更新资产
        user = User.from_dict(user_data)
        user.balance += amount
        user.total_assets += amount # 同时也增加总资产
        
        self.storage.save_user(user_id, user.to_dict())
        
        yield MessageEventResult().message(
            f"✅ 入金成功！\n"
            f"💰 存入金额: {Formatters.format_currency(amount)}元\n"
            f"💵 当前可用: {Formatters.format_currency(user.balance)}元"
        )

    async def handle_withdraw(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """股票出金"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册，请先使用 /股票注册")
            return

        parts = event.message_str.strip().split()
        if len(parts) < 2:
            yield MessageEventResult().message("❌ 参数错误，格式: /股票出金 <金额>")
            return
            
        try:
            amount = float(parts[1])
            if amount <= 0:
                yield MessageEventResult().message("❌ 金额必须大于0")
                return
        except ValueError:
            yield MessageEventResult().message("❌ 金额格式错误")
            return
            
        user = User.from_dict(user_data)
        if user.balance < amount:
            yield MessageEventResult().message(
                f"❌ 余额不足！\n"
                f"当前可用: {Formatters.format_currency(user.balance)}元"
            )
            return

        # 更新资产
        user.balance -= amount
        user.total_assets -= amount
        
        self.storage.save_user(user_id, user.to_dict())
        
        yield MessageEventResult().message(
            f"✅ 出金成功！\n"
            f"💸 取出金额: {Formatters.format_currency(amount)}元\n"
            f"💵 当前可用: {Formatters.format_currency(user.balance)}元"
        )

    async def handle_reset(self, event: AstrMessageEvent) -> AsyncGenerator[MessageEventResult, None]:
        """重置账户"""
        user_id = self.trade_coordinator.get_isolated_user_id(event)
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            yield MessageEventResult().message("❌ 您还未注册")
            return
            
        # 确认机制
        confirm, err = await self.user_interaction.wait_for_reset_confirmation(event)
        if not confirm:
            if err:
                yield MessageEventResult().message(f"❌ {err}") 
            else:
                 yield MessageEventResult().message("操作已取消")
            return

        try:
            self.storage.reset_user_data(user_id)
            yield MessageEventResult().message("✅ 账户已重置！所有资产和持仓已清空。")
        except Exception as e:
            logger.error(f"重置账户失败 {user_id}: {e}")
            yield MessageEventResult().message("❌ 重置失败，系统错误")
