"""格式化工具"""
from typing import List, Dict, Any
from datetime import datetime
import time


class Formatters:
    """格式化工具类"""
    
    @staticmethod
    def format_currency(amount: float, precision: int = 2) -> str:
        """格式化货币金额"""
        if amount >= 100000000:  # 1亿
            return f"{amount/100000000:.2f}亿"
        elif amount >= 10000:     # 1万
            return f"{amount/10000:.2f}万"
        else:
            return f"{amount:.{precision}f}"
    
    @staticmethod
    def format_percentage(value: float, precision: int = 2) -> str:
        """格式化百分比"""
        return f"{value:.{precision}f}%"
    
    @staticmethod
    def format_timestamp(timestamp: int) -> str:
        """格式化时间戳"""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    
    @staticmethod
    def format_stock_info(stock_info: Dict[str, Any]) -> str:
        """格式化股票信息"""
        lines = [
            f"📈 {stock_info['name']} ({stock_info['code']})",
            f"💰 当前价: {stock_info['current_price']:.2f}元",
            f"📊 涨跌: {stock_info['change_amount']:+.2f} ({stock_info['change_percent']:+.2f}%)",
            f"📈 最高: {stock_info['high_price']:.2f} 📉 最低: {stock_info['low_price']:.2f}",
            f"💰 成交额: {Formatters.format_currency(stock_info['turnover'])}元"
        ]
        
        if stock_info.get('is_suspended'):
            lines.append("⏸️ 状态: 停牌")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_user_info(user: Dict[str, Any], positions: List[Dict[str, Any]], frozen_funds: float = 0.0) -> str:
        """格式化用户信息（合并持仓、余额、订单查询）"""
        lines = [
            f"👤 账户信息",
            f"💰 可用余额: {Formatters.format_currency(user['balance'])}元",
            f"💎 总资产: {Formatters.format_currency(user['total_assets'])}元"
        ]
        
        # 如果有冻结资金，显示冻结资金信息
        if frozen_funds > 0:
            lines.append(f"🔒 冻结资金: {Formatters.format_currency(frozen_funds)}元 (买入挂单)")
            lines.append(f"💳 实际可用: {Formatters.format_currency(user['balance'])}元")
        
        if positions:
            lines.append("\n📊 持仓详情:")
            total_market_value = 0
            total_profit_loss = 0
            
            for pos in positions:
                if pos['total_volume'] > 0:
                    profit_color = "🟢" if pos['profit_loss'] >= 0 else "🔴"
                    lines.append(
                        f"{profit_color} {pos['stock_name']}({pos['stock_code']})\n"
                        f"   数量: {pos['total_volume']}股 (可卖: {pos['available_volume']}股)\n"
                        f"   成本: {pos['avg_cost']:.2f}元 现价: {pos['last_price']:.2f}元\n"
                        f"   市值: {Formatters.format_currency(pos['market_value'])}元\n"
                        f"   盈亏: {pos['profit_loss']:+.2f}元 ({pos['profit_loss_percent']:+.2f}%)"
                    )
                    total_market_value += pos['market_value']
                    total_profit_loss += pos['profit_loss']
            
            lines.append(f"\n💼 持仓市值: {Formatters.format_currency(total_market_value)}元")
            profit_color = "🟢" if total_profit_loss >= 0 else "🔴"
            lines.append(f"{profit_color} 总盈亏: {total_profit_loss:+.2f}元")
        else:
            lines.append("\n📊 暂无持仓")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_order_info(order: Dict[str, Any]) -> str:
        """格式化订单信息"""
        order_type_icon = "🟢" if order['order_type'] == 'buy' else "🔴"
        status_icons = {
            'pending': '⏳',
            'filled': '✅',
            'cancelled': '❌',
            'partial': '🔄'
        }
        status_icon = status_icons.get(order['status'], '❓')
        
        lines = [
            f"{order_type_icon} {order['stock_name']}({order['stock_code']})",
            f"{status_icon} 状态: {order['status']}",
            f"💰 价格: {order['order_price']:.2f}元",
            f"📊 数量: {order['order_volume']}股"
        ]
        
        if order['filled_volume'] > 0:
            lines.append(f"✅ 已成交: {order['filled_volume']}股")
        
        lines.append(f"⏰ 时间: {Formatters.format_timestamp(order['create_time'])}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_pending_orders(orders: List[Dict[str, Any]]) -> str:
        """格式化待成交订单列表"""
        if not orders:
            return "📋 暂无待成交订单"
        
        lines = ["📋 待成交订单:"]
        for i, order in enumerate(orders, 1):
            order_type_icon = "🟢买入" if order['order_type'] == 'buy' else "🔴卖出"
            lines.append(
                f"{i}. {order_type_icon} {order['stock_name']}({order['stock_code']})\n"
                f"   价格: {order['order_price']:.2f}元 数量: {order['order_volume']}股\n"
                f"   订单号: {order['order_id']}"
            )
        
        return "\n".join(lines)
    
    @staticmethod
    def format_ranking(users_data: List[Dict[str, Any]], current_user_id: str = None,
                       initial_balance: float = 1000000) -> str:
        """格式化排行榜"""
        if not users_data:
            return "📊 暂无排行数据"
        
        sorted_users = sorted(users_data, key=lambda x: x.get('total_assets', 0), reverse=True)
        
        lines = ["🏆 群内排行榜 (按总资产):"]
        
        for i, user in enumerate(sorted_users[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            profit_loss = user.get('total_assets', 0) - initial_balance
            profit_color = "🟢" if profit_loss >= 0 else "🔴"
            
            name_marker = "👑" if user.get('user_id') == current_user_id else ""
            
            lines.append(
                f"{medal} {user.get('username', '匿名用户')}{name_marker}\n"
                f"   💎 总资产: {Formatters.format_currency(user.get('total_assets', 0))}元\n"
                f"   {profit_color} 盈亏: {profit_loss:+.2f}元"
            )
        
        return "\n".join(lines)
    
    @staticmethod
    def format_order_history(history_data: Dict[str, Any]) -> str:
        """格式化历史订单列表"""
        orders = history_data['orders']
        current_page = history_data['current_page']
        total_pages = history_data['total_pages']
        total_count = history_data['total_count']
        
        if not orders:
            return "📋 暂无历史订单记录"
        
        # 状态中文映射
        status_map = {
            'filled': '已成交',
            'cancelled': '已撤销', 
            'partial': '部分成交'
        }
        
        lines = [f"📋 历史订单 (第{current_page}页/共{total_pages}页, 共{total_count}条):"]
        
        for i, order in enumerate(orders, 1):
            order_type_icon = "🟢买入" if order['order_type'] == 'buy' else "🔴卖出"
            status_text = status_map.get(order['status'], order['status'])
            
            # 根据状态选择图标
            status_icon = "✅" if order['status'] == 'filled' else "❌" if order['status'] == 'cancelled' else "🔄"
            
            lines.append(
                f"{i}. {order_type_icon} {order['stock_name']}({order['stock_code']})\n"
                f"   {status_icon} 状态: {status_text}\n"
                f"   💰 价格: {order['order_price']:.2f}元 数量: {order['order_volume']}股\n"
                f"   📅 时间: {Formatters.format_timestamp(order['update_time'])}\n"
                f"   🆔 订单号: {order['order_id']}"
            )
        
        # 添加分页提示
        if total_pages > 1:
            page_info = []
            if history_data['has_prev']:
                page_info.append(f"上一页: /历史订单 {current_page - 1}")
            if history_data['has_next']:
                page_info.append(f"下一页: /历史订单 {current_page + 1}")
            
            if page_info:
                lines.append("\n" + " | ".join(page_info))
        
        return "\n".join(lines)
    
    @staticmethod
    def format_help_message() -> str:
        """格式化帮助信息"""
        return """📖 papertrading 使用说明

🚀 快速开始:
/股票注册 - 开通模拟交易账户

💰 交易指令:
/买入 股票 数量 - 市价买入
  例: /买入 平安银行 1000
  例: /买入 000001 1000

/限价买入 股票 数量 价格 - 挂单买入
  例: /限价买入 平安银行 1000 12.50
  例: /限价买入 茅台 100 涨停

/卖出 股票 数量 - 市价卖出
/限价卖出 股票 数量 价格 - 挂单卖出

/股票撤单 订单号 - 撤销挂单

📊 查询指令:
/股票账户 - 查询持仓、余额、订单
/股价 股票 - 实时股价  
/股票排行 - 群内排行
/历史订单 - 历史成交记录

⚠️ 交易规则:
• 最小交易单位: 100股（1手）
• T+1制度: 当日买入次日才能卖出
• 涨跌停限制
• 停牌股票无法交易
• 手续费: 0.03%(最低5元)

💡 提示:
• 支持股票名称模糊匹配，如"平安"、"茅台"
• 支持隔夜挂单，非交易时间也可下单
• 限价单支持"涨停"、"跌停"快捷输入"""
