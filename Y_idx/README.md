## 项目说明

一个基于 Binance USDT 永续数据的市场指标看板。填写 API Key 后安装依赖，直接运行 `kanban.py` 即可启动本地 Web 服务查看看板。

### 1. 填写 Binance API Key

编辑 `yquant/db/models/bn_account.py`，在 `_ACCOUNTS` 中填入你的 API Key 和 Secret（保持账户名 `qqdev` 不变，或自定义后与代码中的 `acc` 保持一致）：

```python
_ACCOUNTS = {
    'qqdev': ('你的_API_KEY', '你的_API_SECRET'),
}
```

注意：仅需在此处填写即可，其他地方无需修改。

### 2. 安装依赖

建议使用独立的 Python 环境（如 conda/venv）。

- 使用 pip（国内源示例）：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  Flask pyecharts pandas numpy matplotlib apscheduler ccxt
```

- 或使用 conda（conda-forge）：

```bash
conda install -y -c conda-forge flask pyecharts pandas numpy matplotlib apscheduler ccxt
```

如使用已有 conda 环境，先激活环境后再安装：

```bash
conda activate <你的环境名>
```

### 3. 运行

在项目根目录（包含 `kanban.py` 的目录）执行：

```bash
python kanban.py
```

启动成功后，浏览器访问：

- `http://127.0.0.1:5280/`

### 4. 运行说明

- 首次启动会先执行一次数据更新，向 Binance 拉取历史数据并计算指标，耗时取决于网络与机器性能。
- 生成的数据会保存为若干 CSV（如 `Y_idx.csv`、`volatility_index.csv`、`liquidity_index.csv`、`market_breadth_index.csv` 等）。
- 内置定时任务每天 08:08 自动更新一次数据（参见 `kanban.py` 中 APScheduler 配置）。
- 页面模板位于 `templates/index.html`。

### 5. 常见问题

- 若启动后无法访问页面，确认本地 5280 端口未被占用，或修改 `kanban.py` 中 `app.run(host='0.0.0.0', port=5280)` 的端口。
- 若因网络原因访问 Binance 失败，可在你本地的配置中设置代理（项目代码支持从配置读取代理，具体见 `yquant/common/config` 及相关引用）。

### 6. 目录结构（节选）

```
Y_idx/
  kanban.py
  templates/
    index.html
  yquant/
    db/models/bn_account.py
    common/
    config/
  # 若干生成的 *.csv 与 *.png 文件
```


