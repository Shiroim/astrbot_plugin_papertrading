"""东方财富API服务类"""
import json
import asyncio
from typing import Optional, Dict, Any, Tuple
from astrbot.api import logger

try:
    import aiohttp
except ImportError:
    aiohttp = None


class _RetryContextManager:
    """包装 aiohttp 响应，支持 async with 协议"""
    def __init__(self, cm, resp):
        self._cm = cm
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._cm.__aexit__(exc_type, exc_val, exc_tb)


class EastMoneyAPIService:
    """东方财富API服务"""

    def __init__(self, storage=None):
        self.session = None
        self.storage = storage
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        # 默认API令牌
        self._default_token = 'D43BF722C8E33BDC906FB84D85E326E8'

        # 常用股票代码映射
        self.code_id_dict = {
            '上证综指': '1.000001',
            '上证指数': '1.000001',
            '深证成指': '0.399001',
            '深证指数': '0.399001',
            '创业板指': '0.399006',
            '创业板': '0.399006',
            '沪深300': '1.000300',
            '上证50': '1.000016',
            '科创50': '1.000688',
            '中小100': '0.399005',
            '中小板': '0.399005'
        }

    async def __aenter__(self):
        """异步上下文管理器入口"""
        if aiohttp is None:
            raise ImportError("需要安装aiohttp: pip install aiohttp")

        connector = aiohttp.TCPConnector(
            verify_ssl=False,
            limit=10,
            enable_cleanup_closed=True,
            force_close=True,
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()

    async def _request_with_retry(self, method: str, url: str, max_retries: int = 2, **kwargs):
        """带重试的HTTP请求，处理Server disconnected等瞬态错误。返回 async with 可用的上下文管理器。"""
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                cm = self.session.request(method, url, **kwargs)
                resp = await cm.__aenter__()
                return _RetryContextManager(cm, resp)
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError,
                    aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt < max_retries:
                    wait = 0.5 * (attempt + 1)
                    logger.warning(f"请求 {url} 失败({type(e).__name__})，{wait:.1f}s 后重试({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait)
        raise last_exc

    async def get_code_id(self, code: str) -> Optional[Tuple[str, str]]:
        """
        获取东方财富股票专用的行情ID

        Args:
            code: 股票代码或简称

        Returns:
            (secid, name) 或 None
        """
        # 如果已经是完整的secid格式
        if '.' in code:
            return code, ''

        # 检查预定义映射
        if code in self.code_id_dict:
            return self.code_id_dict[code], code

        # 通过搜索API获取
        url = 'https://searchapi.eastmoney.com/api/suggest/get'
        params = {
            'input': code,
            'type': '14',
            'token': self._get_api_token(),
            'count': '10'
        }

        try:
            async with await self._request_with_retry('GET', url, params=params) as response:
                if response.status == 200:
                    text = await response.text()
                    data = json.loads(text)

                    code_list = data.get('QuotationCodeTable', {}).get('Data', [])
                    if code_list:
                        code_list.sort(
                            key=lambda x: x.get('SecurityTypeName') == '债券'
                        )
                        return code_list[0]['QuoteID'], code_list[0]['Name']

        except Exception as e:
            logger.error(f"搜索股票代码失败 {code}: {e}")

        return None

    async def search_stocks_fuzzy(self, keyword: str) -> list:
        """
        模糊搜索股票，支持中文名称、拼音、代码等

        Args:
            keyword: 搜索关键词（中文名、拼音、代码等）

        Returns:
            股票候选列表，每个元素包含 {'code', 'name', 'market'}
        """
        # 先检查是否为有效的股票代码
        if keyword.isdigit() and len(keyword) == 6:
            from ..utils.validators import Validators
            if Validators.is_valid_stock_code(keyword):
                stock_info = await self.get_stock_realtime_data(keyword)
                if stock_info:
                    return [{
                        'code': keyword,
                        'name': stock_info['name'],
                        'market': self._get_market_name(keyword)
                    }]

        # 通过搜索API进行模糊搜索
        url = 'https://searchapi.eastmoney.com/api/suggest/get'
        params = {
            'input': keyword,
            'type': '14',
            'token': self._get_api_token(),
            'count': '8'
        }

        try:
            async with await self._request_with_retry('GET', url, params=params) as response:
                if response.status == 200:
                    text = await response.text()
                    data = json.loads(text)

                    code_list = data.get('QuotationCodeTable', {}).get('Data', [])
                    if not code_list:
                        return []

                    candidates = []
                    from ..utils.validators import Validators

                    for item in code_list:
                        quote_id = item.get('QuoteID', '')
                        name = item.get('Name', '')
                        security_type = item.get('SecurityTypeName', '')

                        code = quote_id.split('.')[-1] if '.' in quote_id else quote_id

                        if (code.isdigit() and len(code) == 6 and
                            Validators.is_valid_stock_code(code) and
                            security_type != '债券'):

                            candidates.append({
                                'code': code,
                                'name': name,
                                'market': self._get_market_name(code)
                            })

                    seen_codes = set()
                    unique_candidates = []
                    for candidate in candidates:
                        if candidate['code'] not in seen_codes:
                            seen_codes.add(candidate['code'])
                            unique_candidates.append(candidate)
                            if len(unique_candidates) >= 5:
                                break

                    return unique_candidates

        except Exception as e:
            logger.error(f"模糊搜索股票失败 {keyword}: {e}")

        return []

    def _get_api_token(self) -> str:
        """获取API令牌，从配置读取，留空则使用默认值"""
        if self.storage:
            token = self.storage.get_plugin_config_value('eastmoney_api_token', '').strip()
            return token if token else self._default_token
        return self._default_token

    def _get_market_name(self, code: str) -> str:
        """获取市场名称"""
        if code.startswith(('60', '68')):
            return '沪市'
        elif code.startswith(('00', '30')):
            return '深市' if code.startswith('00') else '创业板'
        elif code.startswith(('43', '83', '87')):
            return '北交所'
        else:
            return '未知'

    def _get_full_security_code(self, code: str) -> str:
        """获取完整的证券代码"""
        if '.' not in code:
            if code.startswith(('00', '30', '39')):
                return f"0.{code}"
            elif code.startswith(('60', '68', '51')):
                return f"1.{code}"
            elif code.startswith(('43', '83', '87')):
                return f"0.{code}"
        return code

    async def get_stock_realtime_data(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时数据

        Args:
            stock_code: 股票代码

        Returns:
            股票实时数据字典或None
        """
        try:
            code_result = await self.get_code_id(stock_code)
            if not code_result:
                logger.error(f"无法找到股票代码: {stock_code}")
                return None

            secid, stock_name = code_result
            secid = self._get_full_security_code(secid)

            url = 'https://push2.eastmoney.com/api/qt/stock/get'
            fields = [
                'f58',  # 股票名称
                'f57',  # 股票代码
                'f43',  # 最新价(元)
                'f44',  # 最高价(元)
                'f45',  # 最低价(元)
                'f46',  # 开盘价(元)
                'f60',  # 昨收价(元)
                'f47',  # 成交量(手)
                'f48',  # 成交额(元)
                'f169', # 涨跌额(元)
                'f170', # 涨跌幅(%)
                'f51',  # 涨停价(元)
                'f52',  # 跌停价(元)
                'f86',  # 时间戳
            ]

            params = {
                'fields': ','.join(fields),
                'secid': secid
            }

            async with await self._request_with_retry('GET', url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get('data') is None:
                        logger.error(f"获取股票数据失败，可能股票不存在: {stock_code}")
                        return None

                    raw_data = data['data']

                    result = {
                        'code': stock_code,
                        'name': raw_data.get('f58', stock_name),
                        'current_price': float(raw_data.get('f43', 0) or 0) / 100,
                        'open_price': float(raw_data.get('f46', 0) or 0) / 100,
                        'close_price': float(raw_data.get('f60', 0) or 0) / 100,
                        'high_price': float(raw_data.get('f44', 0) or 0) / 100,
                        'low_price': float(raw_data.get('f45', 0) or 0) / 100,
                        'volume': int(raw_data.get('f47', 0) or 0),
                        'turnover': float(raw_data.get('f48', 0) or 0),
                        'change_amount': float(raw_data.get('f169', 0) or 0) / 100,
                        'change_percent': float(raw_data.get('f170', 0) or 0) / 100,
                        'limit_up': float(raw_data.get('f51', 0) or 0) / 100,
                        'limit_down': float(raw_data.get('f52', 0) or 0) / 100,
                        'timestamp': raw_data.get('f86', ''),
                    }

                    return result
                else:
                    logger.error(f"请求失败，状态码: {response.status}")
                    return None

        except Exception as e:
            logger.error(f"获取股票实时数据失败 {stock_code}: {e}")
            return None

    async def batch_get_stocks_data(self, stock_codes: list) -> Dict[str, Dict[str, Any]]:
        """
        批量获取股票数据

        Args:
            stock_codes: 股票代码列表

        Returns:
            {stock_code: stock_data} 字典
        """
        results = {}

        async def _fetch_one(code: str):
            data = await self.get_stock_realtime_data(code)
            await asyncio.sleep(0.1)
            return code, data

        tasks = [_fetch_one(code) for code in stock_codes]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, Exception):
                logger.error(f"批量获取股票数据失败: {result}")
            elif result:
                code, data = result
                if data:
                    results[code] = data

        return results


# 全局API实例（单例模式）
_api_instance = None

async def get_eastmoney_api() -> EastMoneyAPIService:
    """获取东方财富API实例"""
    global _api_instance
    if _api_instance is None:
        _api_instance = EastMoneyAPIService()
    return _api_instance
