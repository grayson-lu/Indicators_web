'''
币安工具函数
'''
import time
import pandas as pd
from datetime import datetime, timedelta
import traceback
from joblib import Parallel, delayed
import requests

def robust_(func, params=None, func_name='', max_retries=5, base_delay=2):
    """
    健壮的API调用函数 - 增强版
    
    Args:
        func: 要调用的函数
        params: 函数参数
        func_name: 函数名称（用于日志）
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
    
    Returns:
        函数调用结果
    """
    for i in range(max_retries):
        try:
            result = func() if params is None else func(params)
            if i > 0:  # 如果之前有失败，记录成功信息
                print(f'{func_name} 第{i+1}次调用成功')
            return result
        except Exception as e:
            error_msg = str(e)
            print(f'{func_name} 第{i+1}次调用失败: {error_msg}')
            
            # 如果是最后一次重试，直接抛出异常
            if i == max_retries - 1:
                raise Exception(f'{func_name} 调用失败，已重试{max_retries}次')
            
            # 根据错误类型调整延迟时间
            if 'timeout' in error_msg.lower() or 'connection' in error_msg.lower():
                delay = base_delay * (2 ** i)  # 指数退避
            else:
                delay = base_delay
            
            print(f'等待 {delay} 秒后重试...')
            time.sleep(delay)

def test_network_connectivity():
    """
    测试网络连接性
    
    Returns:
        tuple: (是否连通, 错误信息)
    """
    test_urls = [
        'https://fapi.binance.com/fapi/v1/ping',
        'https://api.binance.com/api/v3/ping',
        'https://www.google.com',
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"网络连接正常: {url}")
                return True, None
        except Exception as e:
            print(f"连接失败 {url}: {str(e)}")
            continue
    
    return False, "所有测试URL连接失败"

def u_furture_get_exchangeinfo(exchange):
    """
    获取U本位合约交易规则 - 增强版
    
    Args:
        exchange: ccxt.binance 实例
        
    Returns:
        dict: 包含交易规则的字典，主要包含 symbols 列表，每个symbol包含：
            - symbol: 交易对名称
            - status: 交易状态
            - baseAsset: 基础资产
            - quoteAsset: 报价资产
            - contractType: 合约类型
            - onboardDate: 上线时间
    """
    try:
        # 首先测试网络连接
        is_connected, error = test_network_connectivity()
        if not is_connected:
            print(f"网络连接测试失败: {error}")
            print("尝试使用备用方法...")
        
        # 尝试多种方法获取交易所信息
        methods = [
            ('fapiPublicGetExchangeInfo', {}),
            ('publicGetExchangeInfo', {}),
        ]
        
        for method_name, params in methods:
            if hasattr(exchange, method_name):
                try:
                    print(f"尝试使用方法: {method_name}")
                    method = getattr(exchange, method_name)
                    exchange_info = robust_(method, params, func_name=method_name, max_retries=3, base_delay=3)
                    
                    if exchange_info and 'symbols' in exchange_info:
                        print(f"成功获取交易所信息，共{len(exchange_info['symbols'])}个交易对")
                        return exchange_info
                        
                except Exception as e:
                    print(f"方法 {method_name} 失败: {str(e)}")
                    continue
        
        print("所有方法都失败，返回None")
        return None
        
    except Exception as e:
        print(f"获取交易规则失败: {str(e)}")
        traceback.print_exc()
        return None

def process_single_symbol(args):
    """
    处理单个交易对的K线数据获取
    用于多进程调用
    """
    import ccxt
    from yquant.config.config import cfg  # 导入配置
    
    # 创建新的exchange实例并设置完整配置
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'timeout': cfg.binance.timeout,
        'rateLimit': cfg.binance.rateLimit,
        'verbose': cfg.binance.verbose,
        'hostname': cfg.binance.hostname,
        'proxies': cfg.binance.proxies,  # 添加代理配置
    })

    symbol, run_time, limit, interval = args  # 解包时添加interval
    return fetch_binance_swap_candle_data(exchange, symbol, run_time, limit, interval)

def u_furture_fetch_all_swap_candle_data(exchange, symbol_list, interval, run_time, limit, include_now=True, is_swap=True, njobs=8):
    """
    批量获取U本位合约K线数据

    Args:
        exchange: ccxt交易所实例
        symbol_list: 交易对列表
        interval: K线间隔
        run_time: 运行时间
        limit: K线数量限制
        include_now: 是否包含当前K线
        is_swap: 是否为永续合约
        njobs: 进程数

    Returns:
        dict: {symbol: DataFrame}
    """
    result = []
    # symbol_list = symbol_list[:4]
    if njobs == 1:
        # 单进程获取数据
        for symbol in symbol_list:
            res = fetch_binance_swap_candle_data(exchange, symbol, run_time, limit, interval)
            if res[1] is not None:  # 只添加成功获取的数据
                result.append(res)

    else:
        # 使用joblib进行多进程处理
        arg_list = [(symbol, run_time, limit, interval) for symbol in symbol_list]
        result = Parallel(n_jobs=njobs, verbose=10)(
            delayed(process_single_symbol)(args) for args in arg_list
        )
        # 过滤掉失败的结果
        result = [r for r in result if r[1] is not None]

    
    return dict(result)

def fetch_binance_swap_candle_data(exchange, symbol, run_time, limit, interval='1h'):
    """
    获取币安U本位合约K线数据
    
    Args:
        exchange: ccxt交易所对象
        symbol: 交易对名称 (如 'BTCUSDT')
        run_time: 截止时间
        limit: K线数量限制
        interval: K线间隔 ('1h', '1d')
    
    Returns:
        tuple: (symbol, DataFrame)
            - symbol: 交易对名称
            - DataFrame: K线数据，如果获取失败则为None
    """
    try:
        kline = []
        remain_limit = limit
        
        # 根据interval调整时间计算
        current_time = datetime.now()
        if interval == '1h':
            start_time = int((current_time - timedelta(hours=limit)).timestamp() * 1000)
        elif interval == '1d':
            start_time = int((current_time - timedelta(days=limit)).timestamp() * 1000)
        else:
            raise ValueError(f"不支持的时间间隔: {interval}")
            
        cur_start_time = start_time
        
        # 处理交易对格式 - 确保格式正确
        # 对于连续合约API，需要使用基础交易对名称（去掉USDT后缀）
        if symbol.endswith('USDT'):
            pair_name = symbol[:-4]  # 去掉'USDT'后缀，如 'BTCUSDT' -> 'BTC'
        else:
            pair_name = symbol
        
        # 定义可用的API方法，按优先级排序
        api_methods = [
            {
                'method': 'fapiPublicGetKlines',
                'params': {
                    'symbol': symbol,
                    'interval': interval,
                    'limit': None,  # 将在循环中设置
                    'startTime': None,  # 将在循环中设置
                }
            },
            {
                'method': 'fapiPublicGetContinuousKlines',
                'params': {
                    'pair': pair_name,
                    'contractType': 'PERPETUAL',
                    'interval': interval,
                    'limit': None,  # 将在循环中设置
                    'startTime': None,  # 将在循环中设置
                }
            }
        ]
        
        # 尝试每个API方法
        success = False
        last_error = None
        
        for api_config in api_methods:
            method_name = api_config['method']
            
            # 检查交易所是否支持该方法
            if not hasattr(exchange, method_name):
                print(f"交易所不支持方法: {method_name}")
                continue
                
            print(f"尝试使用API方法: {method_name}")
            
            try:
                # 重置变量
                kline = []
                remain_limit = limit
                cur_start_time = start_time
                working_params = api_config['params'].copy()
                
                # 获取数据循环
                while remain_limit > 0:
                    cur_limit = min(remain_limit, 499)
                    
                    # 更新参数
                    working_params['limit'] = cur_limit
                    working_params['startTime'] = cur_start_time
                    
                    try:
                        cur_kline = robust_(getattr(exchange, method_name), params=working_params,
                                          func_name=method_name, max_retries=3, base_delay=2)
                        
                        if cur_kline and len(cur_kline) > 0:
                            kline.extend(cur_kline)
                            remain_limit -= cur_limit
                            cur_start_time = int(cur_kline[-1][0]) + 1
                        else:
                            print(f"API返回空数据，停止获取 {symbol}")
                            break
                            
                    except Exception as api_error:
                        print(f"API调用失败 {symbol} (方法: {method_name}): {str(api_error)}")
                        last_error = api_error
                        # 如果是Invalid pair错误，直接尝试下一个方法
                        if "Invalid pair" in str(api_error) or "-4144" in str(api_error):
                            print(f"交易对格式错误，尝试下一个API方法")
                            break
                        else:
                            # 其他错误也跳出内层循环，尝试下一个方法
                            break
                
                # 如果成功获取到数据，标记成功并跳出外层循环
                if kline:
                    success = True
                    print(f"使用 {method_name} 成功获取到 {len(kline)} 条K线数据")
                    break
                    
            except Exception as method_error:
                print(f"方法 {method_name} 执行失败: {str(method_error)}")
                last_error = method_error
                continue

        # 如果所有方法都失败了
        if not success or not kline:
            print(f"所有API方法都失败，无法获取{symbol}的K线数据")
            if last_error:
                print(f"最后一个错误: {str(last_error)}")
            return symbol, None
            
        # 将数据转换为DataFrame
        columns = [
            'timestamp',
            'open',
            'high',
            'low',
            'close',
            'volume',
            'close_time',
            'quote_volume',
            'trades',
            'taker_buy_volume',
            'taker_buy_quote_volume',
            'ignore'
        ]
        df = pd.DataFrame(kline, columns=columns, dtype='float')

        # 处理数据类型
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        # 重命名和整理列
        df = df.rename(columns={'timestamp': 'candle_begin_time'})
        df['symbol'] = symbol
        df = df[[
            'candle_begin_time',
            'open',
            'high',
            'low',
            'close',
            'volume',
            'quote_volume',
            'symbol'
        ]]
        
        print(f"成功获取{symbol}的K线数据，共{len(df)}条记录")
        return symbol, df
        
    except Exception as e:
        print(f"获取{symbol}的K线数据失败: {str(e)}")
        traceback.print_exc()
        return symbol, None


def get_usdt_swap_symbols(exchange):
    """
    获取所有USDT永续合约交易对列表
    
    Args:
        exchange: ccxt.binance 实例
        
    Returns:
        list: USDT永续合约交易对列表，例如 ['BTCUSDT', 'ETHUSDT', ...]
    """
    try:
        # 获取交易所信息
        exchange_info = u_furture_get_exchangeinfo(exchange)
        
        if exchange_info is None or 'symbols' not in exchange_info:
            print("获取交易所信息失败")
            return []
        
        usdt_symbols = []
        
        # 遍历所有交易对，筛选出USDT永续合约
        for symbol_info in exchange_info['symbols']:
            symbol = symbol_info.get('symbol', '')
            status = symbol_info.get('status', '')
            contract_type = symbol_info.get('contractType', '')
            quote_asset = symbol_info.get('quoteAsset', '')
            
            # 筛选条件：
            # 1. 交易状态为TRADING
            # 2. 合约类型为PERPETUAL（永续合约）
            # 3. 报价资产为USDT
            if (status == 'TRADING' and 
                contract_type == 'PERPETUAL' and 
                quote_asset == 'USDT'):
                usdt_symbols.append(symbol)
        
        print(f"获取到 {len(usdt_symbols)} 个USDT永续合约交易对")
        return usdt_symbols
        
    except Exception as e:
        print(f"获取USDT永续合约交易对失败: {str(e)}")
        traceback.print_exc()
        return []

def get_usdt_swap_symbols_fallback():
    """
    获取USDT永续合约交易对列表的备用方案
    当网络连接失败时使用预定义的主要交易对列表
    
    Returns:
        list: 主要USDT永续合约交易对列表
    """
    # 主要的USDT永续合约交易对
    major_usdt_symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT',
        'SOLUSDT', 'DOTUSDT', 'DOGEUSDT', 'AVAXUSDT', 'SHIBUSDT',
        'MATICUSDT', 'LTCUSDT', 'UNIUSDT', 'LINKUSDT', 'ATOMUSDT',
        'ETCUSDT', 'XLMUSDT', 'BCHUSDT', 'FILUSDT', 'TRXUSDT',
        'EOSUSDT', 'AAVEUSDT', 'GRTUSDT', 'VETUSDT', 'FTMUSDT',
        'ALGOUSDT', 'KSMUSDT', 'WAVESUSDT', 'AXSUSDT', 'SANDUSDT',
        'MANAUSDT', 'IOTAUSDT', 'ZILUSDT', 'BATUSDT', 'ZECUSDT',
        'DASHUSDT', 'NEOUSDT', 'ENJUSDT', 'CHZUSDT', 'MKRUSDT',
        'COMPUSDT', 'YFIUSDT', 'SNXUSDT', 'UMAUSDT', 'CRVUSDT',
        'BALUSDT', 'STORJUSDT', 'KNCUSDT', 'FLMUSDT', 'SCUSDT',
        'ZENUSDT', 'ONTUSDT', 'QTUMUSDT', 'ICXUSDT', 'RVNUSDT'
    ]
    
    print(f"使用备用交易对列表，共 {len(major_usdt_symbols)} 个交易对")
    return major_usdt_symbols

def get_usdt_swap_symbols_robust(exchange):
    """
    健壮的获取USDT永续合约交易对列表函数
    优先尝试从API获取，失败时使用备用列表
    
    Args:
        exchange: ccxt.binance 实例
        
    Returns:
        list: USDT永续合约交易对列表
    """
    try:
        print("开始获取USDT永续合约交易对列表...")
        
        # 首先尝试从API获取
        symbols = get_usdt_swap_symbols(exchange)
        
        # 如果获取成功且有数据，返回结果
        if symbols and len(symbols) > 0:
            print(f"API获取成功，共{len(symbols)}个交易对")
            return symbols
        else:
            print("API返回空列表，使用备用交易对列表")
            return get_usdt_swap_symbols_fallback()
            
    except Exception as e:
        print(f"API获取失败: {str(e)}，使用备用交易对列表")
        return get_usdt_swap_symbols_fallback()