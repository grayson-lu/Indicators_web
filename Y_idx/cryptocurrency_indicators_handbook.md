# 加密货币市场指标完全手册

## 目录

1. [概述](#概述)
2. [价值类指标](#价值类指标)
3. [技术分析指标](#技术分析指标)
4. [市场结构指标](#市场结构指标)
5. [情绪与流动性指标](#情绪与流动性指标)
6. [链上数据指标](#链上数据指标)
7. [风险管理指标](#风险管理指标)
8. [综合性指标](#综合性指标)
9. [指标组合建议](#指标组合建议)
10. [技术实现](#技术实现)

---

## 概述

本手册收录了20+个核心加密货币市场指标，涵盖价值分析、技术分析、市场结构、情绪监控、链上数据、风险管理等多个维度。每个指标都包含详细的原理说明、计算方法、信号解读和实际应用建议。

### 指标分类体系

- **价值类指标**: MVRV、AHR999、BTC彩虹价表
- **技术分析**: RSI、MACD、移动平均、动量指标
- **市场结构**: 山寨指数、横截面差异、市场宽度
- **情绪流动性**: 资金费率、盘口价差、恐贪指数
- **链上数据**: 稳定币供应量、交易所流量
- **风险管理**: 波动率指数、极端波动比例
- **综合指标**: Y指数、市场深度指数

---

## 价值类指标

### 1. MVRV指标 (Market Value to Realized Value)

**指标原理**:
MVRV比率通过比较市场价值与实现价值来评估加密货币的估值水平。实现价值代表所有币的最后移动价格，反映市场的真实成本基础。

**计算方法**:
```python
# 基础MVRV计算
mvrv_ratio = market_value / realized_value

# 多窗口期MVRV
for window in [30, 90, 365]:
    realized_value = price.rolling(window).mean()
    mvrv_ratio = current_price / realized_value
    
# MVRV Z-Score标准化
mvrv_zscore = (mvrv_ratio - mvrv_mean) / mvrv_std
```

**信号分级**:
- **极度低估** (< 0.8): 历史大底区域，长期投资机会
- **低估** (0.8-1.0): 相对低位，可考虑逐步建仓
- **合理** (1.0-1.5): 估值合理，持仓观望
- **高估** (1.5-2.5): 估值偏高，注意风险控制
- **极度高估** (> 2.5): 历史高位区域，建议减仓

**应用场景**:
- 长期投资的买卖点判断
- 市场周期性高低点识别
- 投资组合风险管理
- 定投策略的买入强度调整

### 2. AHR999指标

**指标原理**:
AHR999是专门针对比特币设计的囤币指标，通过比较BTC价格与200日定投成本和拟合价格的比率来判断买卖时机。

**计算方法**:
```python
# 200日定投成本
investment_cost_200d = btc_price.rolling(200).mean()

# 拟合价格(指数增长模型)
days_since_genesis = (current_date - btc_genesis_date).days
fitted_price = 10**((days_since_genesis/365) * 5.84 - 17.01)

# AHR999计算
ahr999 = (btc_price / investment_cost_200d) * (btc_price / fitted_price)
```

**信号分级**:
- **抄底区** (< 0.45): 极佳买入机会，建议大力买入
- **定投区** (0.45-1.2): 适合定期投资，正常买入
- **观望区** (1.2-5.0): 市场相对高位，观望为主
- **逃顶区** (> 5.0): 泡沫区域，建议卖出

**特色功能**:
- 基于比特币历史规律设计
- 结合定投成本和增长模型
- 提供明确的操作建议
- 适合长期价值投资者

### 3. MVRVY指数

**指标原理**:
MVRVY指数是基于MVRV的收益率指标，用于衡量市场价值相对于实现价值的收益情况，提供更敏感的市场状态判断。

**计算方法**:
```python
# MVRV比率计算
mvrv_ratio = market_value / realized_value

# MVRVY收益率
mvrvy_return = (mvrv_ratio - 1) * 100

# MVRV Z-Score
mvrv_zscore = (mvrv_ratio - mvrv_mean) / mvrv_std

# 趋势判断
mvrv_trend = mvrvy_return.pct_change()
```

**信号解读**:
- **MVRVY > 50%**: 市场过热，谨慎操作
- **MVRVY 0-50%**: 正常上涨，持续关注
- **MVRVY -20-0%**: 调整阶段，逢低吸纳
- **MVRVY < -20%**: 深度调整，分批建仓

---

## 技术分析指标

### 4. 市场宽度指数

**指标原理**:
通过统计不同价格水平上币种的分布情况，衡量市场参与的广度和深度，识别市场的健康程度和潜在转折点。

**计算方法**:
```python
# 涨跌比例统计
rising_count = len(df[df['price_change'] > 0])
falling_count = len(df[df['price_change'] < 0])
breadth_ratio = rising_count / (rising_count + falling_count)

# 多周期创新高占比
for period in [7, 30, 90, 365]:
    new_high_count = len(df[df['close'] == df['close'].rolling(period).max()])
    new_high_ratio = new_high_count / len(df)

# 均线宽度指数
ma_above_5d = len(df[df['close'] > df['ma_5']])
ma_above_20d = len(df[df['close'] > df['ma_20']])
ma_breadth_index = (ma_above_5d + ma_above_20d) / (2 * len(df))
```

**核心指标**:
- **涨跌比例**: 反映市场整体方向
- **创新高占比**: 衡量上涨质量
- **均线宽度**: 判断趋势强度
- **AD百分比**: 上涨下跌币种比例

**信号判断**:
- **宽度 > 70%**: 强势上涨，市场健康
- **宽度 50-70%**: 正常上涨，保持关注
- **宽度 30-50%**: 震荡整理，选择方向
- **宽度 < 30%**: 弱势下跌，规避风险

### 5. 横截面差异指数

**指标原理**:
通过计算不同币种之间收益率的差异程度，衡量市场分化状况，识别板块轮动和风格切换。

**计算方法**:
```python
# 收益率标准差
returns_std = daily_returns.std(axis=1)

# 变异系数
coefficient_variation = returns_std / abs(daily_returns.mean(axis=1))

# 四分位距
q75 = daily_returns.quantile(0.75, axis=1)
q25 = daily_returns.quantile(0.25, axis=1)
iqr = q75 - q25

# 基尼系数
def gini_coefficient(x):
    sorted_x = np.sort(x)
    n = len(x)
    cumsum = np.cumsum(sorted_x)
    return (2 * np.sum((np.arange(1, n+1) * sorted_x))) / (n * cumsum[-1]) - (n+1)/n

# 综合差异指数
cross_section_diff = (returns_std * 0.4 + coefficient_variation * 0.3 + 
                     iqr * 0.2 + gini_coefficient * 0.1)
```

**应用价值**:
- **高差异**: 个股分化明显，精选个股机会
- **低差异**: 系统性行情，指数化投资
- **差异扩大**: 市场风格切换
- **差异收敛**: 方向性行情启动

### 6. 极端波动比例指标

**指标原理**:
统计市场中出现极端涨跌幅的币种占比，评估市场极端情绪和风险水平。

**计算方法**:
```python
# 设定极端阈值
extreme_up_threshold = 20.0    # 爆拉阈值
extreme_down_threshold = -15.0  # 暴跌阈值

# 统计极端币种
extreme_up_count = len(df[df['price_change'] >= extreme_up_threshold])
extreme_down_count = len(df[df['price_change'] <= extreme_down_threshold])

# 计算占比
extreme_up_ratio = extreme_up_count / len(df) * 100
extreme_down_ratio = extreme_down_count / len(df) * 100

# 爆拉暴跌比率
extreme_ratio = extreme_up_count / (extreme_down_count + 1e-10)

# 平均极端程度
avg_extreme_up = df[df['price_change'] >= extreme_up_threshold]['price_change'].mean()
avg_extreme_down = df[df['price_change'] <= extreme_down_threshold]['price_change'].mean()
```

**风险等级**:
- **低风险** (< 5%): 市场平稳，正常操作
- **中风险** (5-15%): 波动加大，谨慎操作
- **高风险** (15-30%): 市场躁动，控制仓位
- **极高风险** (> 30%): 极端行情，空仓观望

---

## 市场结构指标

### 7. 山寨指数

**指标原理**:
通过比较全市场前50涨跌幅名单中跑赢BTC的币种数量，衡量山寨币相对于BTC的表现强度。

**计算方法**:
```python
# 获取涨跌幅排名前50
top_50_gainers = df.nlargest(50, 'price_change')
top_50_losers = df.nsmallest(50, 'price_change')

# 统计跑赢BTC的数量
btc_change = btc_df['price_change'].iloc[-1]
outperform_btc_gainers = len(top_50_gainers[top_50_gainers['price_change'] > btc_change])
outperform_btc_losers = len(top_50_losers[top_50_losers['price_change'] > btc_change])

# 计算山寨指数
altcoin_index = (outperform_btc_gainers + outperform_btc_losers) / 100

# 多周期统计
for period in ['月度', '季度', '年度']:
    period_altcoin_index = calculate_period_index(period)
```

**信号含义**:
- **山寨指数 > 0.7**: 山寨币强势，alt season
- **山寨指数 0.4-0.7**: 山寨币正常表现
- **山寨指数 0.2-0.4**: 山寨币相对弱势
- **山寨指数 < 0.2**: BTC主导，山寨币低迷

### 8. AD百分比指标

**指标原理**:
Advance/Decline百分比通过统计上涨币种数量与下跌币种数量的比例，反映市场整体的强弱程度。

**计算方法**:
```python
# 按成交额筛选活跃币种
active_coins = df[df['volume_rank'] <= 100]

# 统计涨跌情况
advance_count = len(active_coins[active_coins['price_change'] > 0])
decline_count = len(active_coins[active_coins['price_change'] < 0])
unchanged_count = len(active_coins[active_coins['price_change'] == 0])

# 计算AD百分比
ad_percentage = advance_count / (advance_count + decline_count) * 100
ad_ratio = advance_count / (decline_count + 1e-10)

# 净上涨百分比
net_advance_percentage = (advance_count - decline_count) / len(active_coins) * 100

# 多窗口期AD指标
for window in [1, 7, 30]:
    window_ad_percentage = calculate_window_ad(window)
```

**市场强度判断**:
- **强势市场** (AD% > 70%): 普涨行情，追涨操作
- **正常市场** (AD% 45-70%): 平衡市场，精选个股
- **弱势市场** (AD% 30-45%): 震荡调整，控制风险
- **极弱市场** (AD% < 30%): 普跌行情，空仓观望

### 9. 全市场涨跌幅指标

**指标原理**:
统计全市场币种的平均涨跌幅，筛选成交额排名前20的币种，计算其在不同统计周期的平均涨跌幅。

**计算方法**:
```python
# 筛选活跃币种
top_20_volume = df.nlargest(20, 'quote_volume')

# 计算不同周期涨跌幅
for days in [1, 3, 7, 30]:
    period_change = top_20_volume[f'change_{days}d'].mean()
    period_volatility = top_20_volume[f'change_{days}d'].std()
    
# 市场温度计算
market_temperature = calculate_market_temperature(daily_changes)

# 涨跌幅分布
change_distribution = pd.cut(top_20_volume['daily_change'], 
                           bins=[-np.inf, -10, -5, 0, 5, 10, np.inf],
                           labels=['大跌', '中跌', '小跌', '小涨', '中涨', '大涨'])
```

**应用场景**:
- 市场整体趋势判断
- 行情强度评估
- 买卖时机选择
- 风险管理参考

---

## 情绪与流动性指标

### 10. 全市场资金费率监控

**指标原理**:
监控永续合约的资金费率分布，反映市场多空情绪和杠杆使用情况。

**计算方法**:
```python
# 基础统计
funding_rate_mean = funding_rates.mean()
funding_rate_median = funding_rates.median()
funding_rate_std = funding_rates.std()

# 正负费率分布
positive_rate_count = len(funding_rates[funding_rates > 0])
negative_rate_count = len(funding_rates[funding_rates < 0])
positive_rate_ratio = positive_rate_count / len(funding_rates)

# 极端费率检测
high_positive_threshold = funding_rate_mean + 2 * funding_rate_std
high_negative_threshold = funding_rate_mean - 2 * funding_rate_std

extreme_positive_count = len(funding_rates[funding_rates > high_positive_threshold])
extreme_negative_count = len(funding_rates[funding_rates < high_negative_threshold])

# 多空力量评估
long_short_ratio = positive_rate_ratio / (1 - positive_rate_ratio + 1e-10)

# 市场情绪指数
sentiment_score = (positive_rate_ratio - 0.5) * 200  # 转换为-100到100的分数
```

**情绪分级**:
- **极度贪婪** (费率 > 0.1%): 多头过热，注意回调风险
- **贪婪** (费率 0.05-0.1%): 多头情绪浓厚，谨慎追高
- **中性** (费率 -0.05-0.05%): 市场平衡，正常操作
- **恐惧** (费率 -0.1--0.05%): 空头情绪升温，寻找机会
- **极度恐惧** (费率 < -0.1%): 过度悲观，抄底时机

### 11. 盘口价差监控

**指标原理**:
通过监控买卖价差来评估市场流动性状况和交易成本。

**计算方法**:
```python
# 相对价差计算
relative_spread = (ask_price - bid_price) / ((ask_price + bid_price) / 2) * 100

# 价差波动率
spread_volatility = relative_spread.rolling(24).std()

# 流动性评分
def calculate_liquidity_score(spread, volume):
    # 价差越小，成交量越大，流动性越好
    volume_score = np.log(volume + 1)
    spread_score = 1 / (spread + 0.001)
    return volume_score * spread_score

liquidity_score = calculate_liquidity_score(relative_spread, volume)

# 交易成本评估
trading_cost = relative_spread / 2  # 单向交易成本

# 流动性状态判断
def get_liquidity_status(spread, score):
    if spread < 0.05 and score > 80:
        return "极高流动性"
    elif spread < 0.1 and score > 60:
        return "高流动性"
    elif spread < 0.2 and score > 40:
        return "中等流动性"
    elif spread < 0.5 and score > 20:
        return "低流动性"
    else:
        return "极低流动性"
```

**风险等级**:
- **极低风险** (价差 < 0.05%): 流动性充足，正常交易
- **低风险** (价差 0.05-0.1%): 流动性良好，小心滑点
- **中风险** (价差 0.1-0.3%): 流动性一般，控制交易量
- **高风险** (价差 0.3-0.5%): 流动性不足，谨慎交易
- **极高风险** (价差 > 0.5%): 流动性枯竭，暂停交易

### 12. 流动性指数

**指标原理**:
综合考虑价格波动率、成交量、市场深度等因素，计算市场整体流动性水平。

**计算方法**:
```python
# 波动率/成交量比
volatility_volume_ratio = price_volatility / np.log(volume + 1)

# 日内波动/成交量比
intraday_volatility = (high - low) / close
intraday_volume_ratio = intraday_volatility / np.log(volume + 1)

# 市场深度指数
market_depth_index = (bid_volume + ask_volume) / (2 * avg_volume)

# 综合流动性指数
liquidity_index = (
    (1 / volatility_volume_ratio) * 0.4 +
    (1 / intraday_volume_ratio) * 0.3 +
    market_depth_index * 0.3
)

# 标准化处理
normalized_liquidity = (liquidity_index - liquidity_index.mean()) / liquidity_index.std()
```

**支持特性**:
- 1小时和1日双时间粒度
- 多维度流动性评估
- 标准化指数便于比较
- 实时动态更新

### 13. 涨跌比重指标

**指标原理**:
统计市场中不同涨跌幅区间的币种分布比重，分析市场情绪和资金分布。

**计算方法**:
```python
# 定义涨跌幅区间
change_bins = [-np.inf, -20, -10, -5, -2, 0, 2, 5, 10, 20, np.inf]
change_labels = ['暴跌', '大跌', '中跌', '小跌', '微跌', 
                 '微涨', '小涨', '中涨', '大涨', '暴涨']

# 按成交额筛选活跃币种
active_coins = df[df['volume_rank'] <= 100]

# 计算各区间比重
change_distribution = pd.cut(active_coins['price_change'], 
                           bins=change_bins, labels=change_labels)
distribution_ratio = change_distribution.value_counts(normalize=True) * 100

# 涨跌比率
up_count = len(active_coins[active_coins['price_change'] > 0])
down_count = len(active_coins[active_coins['price_change'] < 0])
up_down_ratio = up_count / (down_count + 1e-10)

# 市场情绪指标
market_sentiment = (up_count - down_count) / len(active_coins) * 100
avg_change = active_coins['price_change'].mean()
```

**情绪判断**:
- **极度乐观**: 大涨比重 > 30%
- **乐观**: 上涨比重 > 70%
- **平衡**: 上涨比重 45-70%
- **悲观**: 上涨比重 < 45%
- **极度悲观**: 暴跌比重 > 20%

---

## 链上数据指标

### 14. 稳定币供应量监控

**指标原理**:
监控主要稳定币的链上供应量变化，分析市场流动性和资金流向趋势。

**计算方法**:
```python
# 主要稳定币供应量
stablecoins = ['USDT', 'USDC', 'BUSD', 'DAI', 'FRAX']
total_supply = {}

for coin in stablecoins:
    # 模拟供应量数据
    supply_data = simulate_supply_data(coin, days=365)
    total_supply[coin] = supply_data

# 计算各时间窗口变化
for window in [7, 30, 90]:
    supply_change = {}
    for coin in stablecoins:
        change = total_supply[coin].pct_change(window).iloc[-1] * 100
        supply_change[f'{coin}_{window}d'] = change
    
    # 总供应量变化
    total_change = sum(supply_change.values()) / len(stablecoins)

# 增长率和波动率
for coin in stablecoins:
    growth_rate = total_supply[coin].pct_change().mean() * 365 * 100
    volatility = total_supply[coin].pct_change().std() * np.sqrt(365) * 100

# 市场关联指标
btc_correlation = calculate_correlation(total_supply_change, btc_price_change)

# 综合指标
total_market_cap = sum([supply * price for coin, supply, price in zip(stablecoins, supplies, prices)])
market_share = {coin: (supply * price) / total_market_cap for coin, supply, price in zip(stablecoins, supplies, prices)}
hhi_index = sum([share**2 for share in market_share.values()])  # 市场集中度
```

**状态判断**:
- **供应量增长**: 资金流入，看涨信号
- **供应量收缩**: 资金流出，看跌信号
- **USDT占比上升**: 避险需求增加
- **USDC占比上升**: 机构资金入场

### 15. 交易所净流入流出监控

**指标原理**:
基于成交量加权价格变化计算资金流向，监控资金在交易所的流入流出情况。

**计算方法**:
```python
# 基础指标计算
price_change = close.pct_change()
volume_ma_7 = volume.rolling(7).mean()
volume_ratio = volume / (volume_ma_7 + 1e-10)

# 价格动量指标
price_momentum_3 = close.pct_change(3)
price_momentum_7 = close.pct_change(7)

# 综合流向评分
momentum_score = (price_change * 0.4 + price_momentum_3 * 0.3 + price_momentum_7 * 0.3)
volume_score = np.log1p(volume_ratio)
flow_score = momentum_score * volume_score

# 计算流入流出金额
base_flow = quote_volume * flow_score
flow_smoothed = base_flow.rolling(3).mean()

# 异常值处理
q99 = flow_smoothed.quantile(0.99)
q01 = flow_smoothed.quantile(0.01)
flow_clipped = flow_smoothed.clip(q01, q99)

# 分离流入流出
inflow = np.where(flow_clipped > 0, flow_clipped, 0)
outflow = np.where(flow_clipped < 0, -flow_clipped, 0)
net_flow = inflow - outflow

# 流入流出比率
flow_ratio = (inflow + 1e6) / (outflow + 1e6)
```

**信号解读**:
- **大量净流入**: 看涨信号，资金追涨
- **持续净流入**: 上涨趋势确立
- **流入流出平衡**: 震荡整理
- **大量净流出**: 看跌信号，获利了结
- **持续净流出**: 下跌趋势确立

---

## 风险管理指标

### 16. 截面波动率指数

**指标原理**:
计算加密货币市场的整体波动率水平，评估市场风险程度。

**计算方法**:
```python
# 日收益率计算
daily_returns = close.pct_change()

# 日振幅计算
daily_amplitude = (high - low) / close

# 不同窗口期波动率
for window in [7, 30, 90]:
    # 基于收益率的波动率
    volatility_return = daily_returns.rolling(window).std() * np.sqrt(365) * 100
    
    # 基于振幅的波动率
    volatility_amplitude = daily_amplitude.rolling(window).std() * np.sqrt(365) * 100

# 按成交额筛选活跃币种
active_coins = df[df['volume_rank'] <= 50]

# 市场整体波动率
market_volatility_mean = active_coins['volatility_30d'].mean()
market_volatility_median = active_coins['volatility_30d'].median()

# 高波动币种占比
high_volatility_threshold = market_volatility_mean + market_volatility_std
high_volatility_ratio = len(active_coins[active_coins['volatility_30d'] > high_volatility_threshold]) / len(active_coins)
```

**风险等级**:
- **极低风险** (波动率 < 20%): 市场平稳
- **低风险** (波动率 20-40%): 正常波动
- **中风险** (波动率 40-60%): 波动加大
- **高风险** (波动率 60-80%): 高度波动
- **极高风险** (波动率 > 80%): 极端波动

### 17. 涨跌停比例

**指标原理**:
统计触及涨跌停限制的币种比例，评估市场极端情况。

**核心功能**:
- 统计涨停币种数量和比例
- 统计跌停币种数量和比例
- 计算连续涨跌停天数
- 分析涨跌停分布特征

---

## 综合性指标

### 18. Y指数综合指标

**指标原理**:
整合价格动量、成交量、技术指标、波动率、市场广度等多个维度，提供全面的市场分析视角。

**计算方法**:
```python
# 价格动量得分
momentum_5_score = normalize_score(price_momentum_5.mean(), -10, 10)
momentum_20_score = normalize_score(price_momentum_20.mean(), -30, 30)
price_momentum_score = momentum_5_score * 0.6 + momentum_20_score * 0.4

# 成交量得分
volume_score = normalize_score(volume_ratio.mean(), 0.5, 2.0)

# 技术指标得分
rsi_score = normalize_score(rsi.mean(), 30, 70)
macd_score = normalize_score(macd_histogram.mean(), -0.1, 0.1)
technical_score = rsi_score * 0.5 + macd_score * 0.5

# 波动率得分
volatility_score = normalize_score(100 - volatility_20.mean(), 0, 100)

# 市场广度得分
up_count = len(df[df['price_momentum_5'] > 0])
breadth_score = normalize_score((up_count / len(df)) * 100, 30, 70)

# 综合Y指数
y_index = (price_momentum_score * 0.3 + volume_score * 0.2 + 
          technical_score * 0.2 + volatility_score * 0.15 + breadth_score * 0.15)
```

**信号系统**:
- **强烈看涨** (Y指数 > 80): 多重指标共振向上
- **看涨** (Y指数 60-80): 整体偏多，谨慎乐观
- **中性** (Y指数 40-60): 震荡整理，观望为主
- **看跌** (Y指数 20-40): 整体偏空，控制风险
- **强烈看跌** (Y指数 < 20): 多重指标共振向下

### 19. 高级指标管理器

**指标原理**:
集成价值指标、技术指标、情绪指标、CTA过滤器等多个模块，提供一站式指标分析。

**核心模块**:
- **价值指标**: 市值加权指数、资金流向、价值偏离度、MVRV比率
- **技术指标**: 趋势分析、超买超卖、动态参数、轮动识别
- **情绪指标**: 情绪监控、恐惧贪婪指数、资金流向情绪
- **CTA过滤器**: 趋势过滤、波动率过滤、动量过滤

**应用价值**:
- 多维度市场分析
- 综合信号生成
- 风险评估
- 策略优化

---

## 指标组合建议

### 短线交易组合
- **核心指标**: 市场宽度指数 + 极端波动比例
- **辅助指标**: 资金费率 + 盘口价差
- **风险控制**: 截面波动率指数
- **操作建议**: 关注日内波动，快进快出

### 中线波段组合
- **核心指标**: Y指数 + 横截面差异指数
- **辅助指标**: 交易所净流入 + 山寨指数
- **风险控制**: AD百分比 + 流动性指数
- **操作建议**: 趋势跟踪，波段操作

### 长线价值组合
- **核心指标**: MVRV + AHR999
- **辅助指标**: 稳定币供应量 + 市场涨跌幅
- **风险控制**: 全市场资金费率
- **操作建议**: 价值投资，长期持有

### 风险管理组合
- **核心指标**: 极端波动比例 + 截面波动率
- **辅助指标**: 盘口价差 + 资金费率
- **风险控制**: 涨跌停比例
- **操作建议**: 风险优先，资金保护

---

## 技术实现

### 数据源
- **价格数据**: Binance API
- **成交量数据**: 交易所实时数据
- **链上数据**: 区块链浏览器API
- **资金费率**: 衍生品交易所

### 计算频率
- **实时指标**: 5分钟更新
- **日频指标**: 每日收盘后更新
- **周频指标**: 每周更新
- **月频指标**: 每月更新

### 存储格式
- **数据存储**: CSV文件 + 时序数据库
- **图表输出**: PNG高清图片
- **数据备份**: 本地 + 云端备份

### 技术栈
- **编程语言**: Python 3.8+
- **数据处理**: Pandas + NumPy
- **图表绘制**: Matplotlib + Plotly
- **并行计算**: Multiprocessing
- **API接口**: CCXT + Requests

---

## 更新说明

**版本**: v2.0.0  
**更新日期**: 2024年12月  
**更新内容**:
- 新增5个链上数据指标
- 优化计算性能，支持并行处理
- 增强异常值检测和数据清洗
- 完善信号分级和风险评估
- 新增组合策略建议

**维护说明**:
- 指标算法持续优化
- 阈值参数动态调整
- 新增市场异常处理
- 提升数据质量控制

---

*本手册将根据市场变化和用户反馈持续更新和完善。*