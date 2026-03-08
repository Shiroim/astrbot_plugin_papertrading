# 📈 papertrading 插件

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-green.svg)](https://www.python.org/downloads/)
[![AstrBot](https://img.shields.io/badge/AstrBot-v4.0+-purple.svg)](https://astrbot.app)

为AstrBot提供完整的虚拟炒股功能。支持实时股价、委托交易、持仓管理、群内排行等丰富特性。

## ✨ 功能特色

### 🎯 完整交易体验
- **市价交易**：即时按当前价格买卖股票
- **限价交易**：委托挂单，价格达到后自动执行
- **智能撤单**：灵活撤销未成交的挂单
- **交易规则**：真实模拟A股交易制度，佣金、税费支持自由设置

### 📊 智能数据服务
- **实时行情**：准确的股价数据
- **市场规则**：完整支持涨跌停、停牌等市场状态
- **自动监控**：后台智能监控挂单，自动执行成交

### 🏆 社交互动
- **群内排行**：实时展示群成员交易成果
- **资产统计**：详细的持仓分析和盈亏计算
- **历史记录**：完整的交易历史追溯

## 📦 安装配置

### 系统要求
- Python 3.8 或更高版本
- AstrBot v4.0 或更高版本
- 网络连接

### 安装步骤

1. **克隆插件到AstrBot插件目录**
```bash
cd AstrBot/data/plugins/
git clone https://github.com/Shiroim/astrbot_plugin_papertrading.git
```

2. **安装Python依赖**
```bash
cd astrbot_plugin_papertrading
pip install -r requirements.txt
```

3. **重启AstrBot或热重载插件**


## 🎮 使用指南

### 账户管理
```
/股票注册          # 创建交易账户，获得100万（默认）初始资金
/股票账户          # 查看账户余额、持仓情况、挂单状态
/股票入金 100000   # 增加账户资金（模拟充值）
/股票出金 50000    # 取出账户资金
/股票重置          # ⚠️ 清空账号所有数据重新开始
```

### 股价查询
```
/股价 000001       # 查询平安银行的实时股价
/股价 平安银行      # 支持股票名称查询
/股价 上证指数      # 查询大盘指数
```

### 交易操作
```
/买入 000001 1000           # 市价买入平安银行1000股
/限价买入 000001 1000 10.50  # 挂单买入，价格10.50元
/卖出 000001 500            # 市价卖出500股
/限价卖出 000001 500 11.00   # 挂单卖出，价格11.00元
/股票撤单 12345             # 撤销订单号12345的挂单
```

### 信息查询
```
/股票排行          # 查看本群交易排行榜
/历史订单          # 查看个人交易历史
/股票帮助          # 显示详细帮助信息
```

## 📋 交易规则

| 规则类型 | 说明 |
|---------|------|
| **最小交易量** | 100股（1手） |
| **交易时间** | 工作日 09:30-11:30, 13:00-15:00 |
| **T+1制度** | 当日买入股票次日方可卖出 |
| **涨跌停限制** | 涨停价只能卖出，跌停价只能买入 |
| **停牌处理** | 停牌股票无法交易 |
| **手续费** | 交易金额的0.03%，最低收取5元 |

## 🔧 高级功能

### 自动监控服务
插件自动处理：
- **挂单撮合**：实时监控股价变化，自动执行达价订单
- **市值更新**：自动更新持仓股票的最新市值
- **数据维护**：每日自动清理过期缓存，更新T+1状态

## 👥 贡献指南

欢迎提交问题报告和功能建议。


## 📄 开源许可

本项目采用 [GNU Affero General Public License v3.0](LICENSE) 开源许可证。

## 丨感谢&参考

- [SayuStock](https://github.com/KimigaiiWuyi/SayuStock) - 参考部分代码

## 🔗 相关链接

- [AstrBot官方文档](https://docs.astrbot.app)
- [AstrBot插件开发指南](https://docs.astrbot.app/dev/star/plugin.html)
- [项目GitHub仓库](https://github.com/Shiroim/astrbot_plugin_papertrading)
- [问题反馈](https://github.com/Shiroim/astrbot_plugin_papertrading/issues)