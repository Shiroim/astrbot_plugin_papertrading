"""用户交互服务 - 实现真正的用户等待交互"""
import asyncio
from typing import Optional, Dict, Any, List, Callable, AsyncGenerator
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.utils.session_waiter import SessionWaiter, SessionFilter, session_waiter, SessionController
from astrbot.api.message_components import Plain
from astrbot.core.message.message_event_result import MessageChain


class UserIsolatedSessionFilter(SessionFilter):
    """按用户隔离的会话过滤器，防止群聊中其他用户的消息触发当前用户的交互等待"""

    def filter(self, event: AstrMessageEvent) -> str:
        return f"{event.unified_msg_origin}:{event.get_sender_id()}"


class UserInteractionService:
    """
    用户交互服务
    使用AstrBot的SessionWaiter实现真正的用户等待交互
    """
    
    def __init__(self):
        self.active_sessions = {}
    
    async def wait_for_stock_selection(self, event: AstrMessageEvent, candidates: List[Dict[str, str]], 
                                     action_description: str = "操作") -> tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        等待用户选择股票
        
        Args:
            event: 原始事件
            candidates: 候选股票列表 [{'code', 'name', 'market'}]
            action_description: 操作描述（用于提示）
            
        Returns:
            (选中的股票信息或None, 错误消息或None)
        """
        if not candidates:
            return None, "没有找到候选股票"
        
        if len(candidates) == 1:
            return candidates[0], None
        
        # 构建选择提示
        selection_text = f"🔍 找到多个相关股票，请选择:\n\n"
        for i, candidate in enumerate(candidates[:5], 1):  # 最多显示5个
            selection_text += f"{i}. {candidate['name']} ({candidate['code']}) [{candidate['market']}]\n"
        selection_text += f"\n💡 请回复数字 1-{min(len(candidates), 5)} 选择股票\n"
        selection_text += f'💡 或回复"取消"退出{action_description}'
        
        # 发送选择提示到事件
        try:
            await event.send(MessageChain([Plain(selection_text)]))
        except Exception as e:
            logger.error(f"发送选择提示失败: {e}")
            return None, "发送选择提示失败"
        
        try:
            # 创建会话等待器
            selected_result = None
            
            @session_waiter(timeout=60, record_history_chains=False)
            async def stock_selection_waiter(controller: SessionController, wait_event: AstrMessageEvent):
                nonlocal selected_result
                user_input = wait_event.message_str.strip()
                
                # 检查取消命令
                if user_input.lower() in ['取消', 'cancel', '0', 'q', 'quit']:
                    selected_result = None
                    controller.stop()
                    return
                
                # 尝试解析数字选择
                try:
                    choice_num = int(user_input)
                    if 1 <= choice_num <= min(len(candidates), 5):
                        selected_result = candidates[choice_num - 1]
                        controller.stop()
                        return
                    else:
                        # 无效选择，继续等待
                        await wait_event.send(MessageChain([Plain(f"❌ 无效选择，请输入 1-{min(len(candidates), 5)} 的数字")]))
                        return
                except ValueError:
                    # 非数字输入，继续等待
                    await wait_event.send(MessageChain([Plain('❌ 请输入数字进行选择，或输入"取消"退出')]))
                    return
            
            # 启动等待（使用用户隔离过滤器，防止他人消息触发）
            await stock_selection_waiter(event, session_filter=UserIsolatedSessionFilter())
            if selected_result is None:
                return None, "用户取消选择"
            return selected_result, None
            
        except asyncio.TimeoutError:
            return None, "⏰ 选择超时，操作已取消"
        except Exception as e:
            logger.error(f"等待用户选择股票失败: {e}")
            return None, "❌ 操作出现错误，请重试"
    
    async def wait_for_trade_confirmation(self, event: AstrMessageEvent, trade_info: Dict[str, Any]) -> tuple[Optional[bool], Optional[str]]:
        """
        等待用户确认交易
        
        Args:
            event: 原始事件
            trade_info: 交易信息字典
            
        Returns:
            (确认结果: True(确认)/False(取消)/None(超时), 错误消息或None)
        """
        # 构建确认提示
        confirmation_text = (
            f"{trade_info['confirmation_message']}\n\n"
            f"💡 请回复:\n"
            f'  "确认" 或 "y" - 执行交易\n'
            f'  "取消" 或 "n" - 取消交易'
        )
        
        # 发送确认提示
        try:
            await event.send(MessageChain([Plain(confirmation_text)]))
        except Exception as e:
            logger.error(f"发送确认提示失败: {e}")
            return None, "发送确认提示失败"
        
        try:
            # 创建会话等待器
            confirmation_result = None
            
            @session_waiter(timeout=60, record_history_chains=False)
            async def trade_confirmation_waiter(controller: SessionController, wait_event: AstrMessageEvent):
                nonlocal confirmation_result
                user_input = wait_event.message_str.strip().lower()
                
                # 检查确认命令
                if user_input in ['确认', 'confirm', 'y', 'yes', '是', '1']:
                    confirmation_result = True
                    controller.stop()
                    return
                
                # 检查取消命令
                if user_input in ['取消', 'cancel', 'n', 'no', '否', '0']:
                    confirmation_result = False
                    controller.stop()
                    return
                
                # 无效输入，继续等待
                await wait_event.send(MessageChain([Plain('❌ 请回复"确认"或"取消"')]))
                return
            
            # 启动等待（使用用户隔离过滤器，防止他人消息触发）
            await trade_confirmation_waiter(event, session_filter=UserIsolatedSessionFilter())
            return confirmation_result, None
            
        except asyncio.TimeoutError:
            return None, "⏰ 确认超时，交易已取消"
        except Exception as e:
            logger.error(f"等待用户确认交易失败: {e}")
            return None, "❌ 确认过程出现错误，交易已取消"
    
    async def wait_for_text_input(self, event: AstrMessageEvent, prompt: str, 
                                validator: Optional[Callable[[str], bool]] = None,
                                timeout: int = 60) -> tuple[Optional[str], Optional[str]]:
        """
        等待用户文本输入
        
        Args:
            event: 原始事件
            prompt: 输入提示信息
            validator: 输入验证函数（可选）
            timeout: 超时时间（秒）
            
        Returns:
            (用户输入的文本或None, 错误消息或None)
        """
        # 发送输入提示
        try:
            await event.send(MessageChain([Plain(f'{prompt}\n\n💡 输入"取消"可退出')]))
        except Exception as e:
            logger.error(f"发送输入提示失败: {e}")
            return None, "发送输入提示失败"
        
        try:
            # 创建会话等待器
            input_result = None
            
            @session_waiter(timeout=timeout, record_history_chains=False)
            async def text_input_waiter(controller: SessionController, wait_event: AstrMessageEvent):
                nonlocal input_result
                user_input = wait_event.message_str.strip()
                
                # 检查取消命令
                if user_input.lower() in ['取消', 'cancel', 'q', 'quit']:
                    input_result = None
                    controller.stop()
                    return
                
                # 验证输入
                if validator and not validator(user_input):
                    await wait_event.send(MessageChain([Plain("❌ 输入格式不正确，请重新输入")]))
                    return
                
                input_result = user_input
                controller.stop()
                return
            
            # 启动等待（使用用户隔离过滤器，防止他人消息触发）
            await text_input_waiter(event, session_filter=UserIsolatedSessionFilter())
            if input_result is None:
                return None, "用户取消输入"
            return input_result, None
            
        except asyncio.TimeoutError:
            return None, "⏰ 输入超时，操作已取消"
        except Exception as e:
            logger.error(f"等待用户文本输入失败: {e}")
            return None, "❌ 输入过程出现错误，请重试"
    
    async def wait_for_choice_selection(self, event: AstrMessageEvent, prompt: str, 
                                      choices: List[str], timeout: int = 60) -> tuple[Optional[int], Optional[str]]:
        """
        等待用户选择（多选一）
        
        Args:
            event: 原始事件
            prompt: 选择提示信息
            choices: 选项列表
            timeout: 超时时间（秒）
            
        Returns:
            (选择的索引（0-based）或None, 错误消息或None)
        """
        if not choices:
            return None, "没有可选项"
        
        if len(choices) == 1:
            return 0, None
        
        # 构建选择提示
        choice_text = f"{prompt}\n\n"
        for i, choice in enumerate(choices, 1):
            choice_text += f"{i}. {choice}\n"
        choice_text += f'\n💡 请回复数字 1-{len(choices)} 进行选择，或输入"取消"退出'
        
        # 发送选择提示
        try:
            await event.send(MessageChain([Plain(choice_text)]))
        except Exception as e:
            logger.error(f"发送选择提示失败: {e}")
            return None, "发送选择提示失败"
        
        try:
            # 创建会话等待器
            choice_result = None
            
            @session_waiter(timeout=timeout, record_history_chains=False)
            async def choice_selection_waiter(controller: SessionController, wait_event: AstrMessageEvent):
                nonlocal choice_result
                user_input = wait_event.message_str.strip()
                
                # 检查取消命令
                if user_input.lower() in ['取消', 'cancel', '0', 'q', 'quit']:
                    choice_result = None
                    controller.stop()
                    return
                
                # 尝试解析数字选择
                try:
                    choice_num = int(user_input)
                    if 1 <= choice_num <= len(choices):
                        choice_result = choice_num - 1  # 返回0-based索引
                        controller.stop()
                        return
                    else:
                        await wait_event.send(MessageChain([Plain(f"❌ 无效选择，请输入 1-{len(choices)} 的数字")]))
                        return
                except ValueError:
                    await wait_event.send(MessageChain([Plain('❌ 请输入数字进行选择，或输入"取消"退出')]))
                    return
            
            # 启动等待（使用用户隔离过滤器，防止他人消息触发）
            await choice_selection_waiter(event, session_filter=UserIsolatedSessionFilter())
            if choice_result is None:
                return None, "用户取消选择"
            return choice_result, None
            
        except asyncio.TimeoutError:
            return None, "⏰ 选择超时，操作已取消"
        except Exception as e:
            logger.error(f"等待用户选择失败: {e}")
            return None, "❌ 选择过程出现错误，请重试"
    
    def is_session_active(self, session_id: str) -> bool:
        """检查会话是否活跃"""
        return session_id in self.active_sessions
    
    def cleanup_session(self, session_id: str):
        """清理会话"""
        self.active_sessions.pop(session_id, None)
    
    async def send_notification(self, session_id: str, message: str):
        """向指定会话发送通知消息"""
        try:
            from astrbot.core.star.star_tools import StarTools
            
            message_chain = MessageEventResult().message(message)
            success = await StarTools.send_message(session_id, message_chain)
            
            if success:
                logger.debug(f"通知消息已发送到会话: {session_id}")
            else:
                logger.warning(f"发送通知消息失败，会话不存在或无效: {session_id}")
                
        except Exception as e:
            logger.error(f"发送通知消息失败: {e}")
    
    async def batch_send_notifications(self, session_messages: Dict[str, str]):
        """批量发送通知消息"""
        for session_id, message in session_messages.items():
            await self.send_notification(session_id, message)

    async def wait_for_reset_confirmation(self, event: AstrMessageEvent) -> tuple[Optional[bool], Optional[str]]:
        """
        等待用户确认重置
        """
        prompt = (
            "⚠️ 警告：股票重置将清空您的所有资产、持仓和订单记录！\n"
            "此操作不可恢复！\n\n"
            "💡 请回复:\n"
            '  "确认" 或 "y" - 立即重置\n'
            '  "取消" 或 "n" - 取消操作'
        )
        try:
            await event.send(MessageChain([Plain(prompt)]))
        except Exception:
            return None, "发送提示失败"

        try:
            confirmation_result = None
            @session_waiter(timeout=30, record_history_chains=False)
            async def reset_waiter(controller: SessionController, wait_event: AstrMessageEvent):
                nonlocal confirmation_result
                val = wait_event.message_str.strip().lower()
                if val in ['确认', 'y', 'yes', '是']:
                    confirmation_result = True
                    controller.stop()
                elif val in ['取消', 'n', 'no', '否']:
                    confirmation_result = False
                    controller.stop()
                else:
                    await wait_event.send(MessageChain([Plain('❌ 请回复"确认"或"取消"')]))

            await reset_waiter(event, session_filter=UserIsolatedSessionFilter())
            if confirmation_result is None:
                return None, "已取消"
            return confirmation_result, None
        except asyncio.TimeoutError:
            return None, "⏰ 操作超时"
        except Exception as e:
            return None, f"出错: {e}"
