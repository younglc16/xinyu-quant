(() => {
  'use strict';
  const markup = `
    <header class="fp-head">
      <p class="fp-tag">交易纪律 · 仓位与退出</p>
      <h2>3570 建仓 / 3221 减仓</h2>
      <p>先判市场状态，再按成交推进。用同一份规则核对多头持仓。</p>
    </header>
    <div class="fp-rules">
      <div><strong>中性震荡</strong><span>3% → +5% → +7% → +10%（累计25%）</span><small>A股省略最后一档，累计15%</small></div>
      <div><strong>强趋势</strong><span>7% → +10%（累计17%）</span><small>趋势已确认才跳过试仓</small></div>
      <div><strong>高风险</strong><span>仅3%试仓</span><small>不加仓；保护价优先</small></div>
    </div>
    <details class="fp-details"><summary>查看 3221 四段与强势滚动规则</summary>
      <ul>
        <li>标准：浮盈10%–15%首减30%；弱势或震荡可选30%–50%或全退。</li>
        <li>浮盈15%–30%且首减成交后再减20%；留意放量滞涨、上影和冲高回落。</li>
        <li>浮盈30%–50%分段兑现，手动确认新的上涨段和减仓比例。</li>
        <li>超过50%按计划全退或保留10%–30%底仓。</li>
        <li>强势：浮盈20%先减30%；之后相对上次实际减仓价每涨所选10%–15%，再减20%，到目标底仓后按实际盈亏平衡价管理。</li>
      </ul>
      <p>减仓比例按首次减仓前的股数计算；20%硬止损按实际持仓成本计算。已有保护价只能维持或上调。</p>
    </details>
    <form class="fp-form">
      <div class="fp-fields">
        <label>市场状态<select name="regime"><option value="neutral">中性震荡 · 标准</option><option value="strong">强趋势 · 进攻</option><option value="defensive">高风险 · 防御</option></select></label>
        <label>交易市场<select name="market"><option value="us">美股</option><option value="hk">港股</option><option value="cn">A股</option><option value="other">其他市场</option></select></label>
        <label>评估价<input name="price" type="number" min="0" step="any" placeholder="核验后填写" required></label>
        <label>实际平均成本<input name="cost" type="number" min="0" step="any" placeholder="有持仓时填写"></label>
        <label>现持有股数<input name="shares" type="number" min="0" step="1" value="0" required></label>
        <label>预算净资产<input name="equity" type="number" min="0" step="any" placeholder="可选，与价格同币种"></label>
      </div>
      <details class="fp-details"><summary>3570 · 建仓档位和保护价</summary>
        <div class="fp-fields">
          <label>完整成交的买入档数<input name="entry_stage" type="number" min="0" max="4" step="1" value="0" required></label>
          <label>原建仓路径<select name="entry_regime"><option value="">同当前市场状态</option><option value="neutral">中性震荡</option><option value="strong">强趋势</option><option value="defensive">高风险</option></select></label>
          <label>上一有效保护价<input name="stop_price" type="number" min="0" step="any" placeholder="加仓前核对"></label>
        </div>
        <label class="fp-check"><input name="setup_confirmed" type="checkbox">已核对市场状态、价格和本档入场依据</label>
        <label class="fp-check"><input name="add_confirmed" type="checkbox">本次有新的趋势或结构证据，且持仓盈利</label>
      </details>
      <details class="fp-details"><summary>3221 · 成交记录和减仓方案</summary>
        <div class="fp-fields">
          <label>已成交减仓次数<input name="exit_count" type="number" min="0" step="1" value="0" required></label>
          <label>首减前股数<input name="exit_base_shares" type="number" min="1" step="1" placeholder="已减仓时必填"></label>
          <label>上次减仓成交价<input name="last_exit_price" type="number" min="0" step="any"></label>
          <label data-fp-standard>弱势或震荡首减（%）<input name="weak_exit_pct" type="number" min="30" max="100" step="any" placeholder="30–50；100全退"></label>
          <label data-fp-standard>第三段本次减仓（%）<input name="stair_pct" type="number" min="0" max="100" step="any" placeholder="按分段计划填写"></label>
          <label data-fp-strong hidden>强势每轮涨幅（%）<input name="strong_step_pct" type="number" min="10" max="15" step="any" placeholder="10–15"></label>
          <label>最终保留底仓（%）<input name="retain_pct" type="number" min="0" max="30" step="any" placeholder="默认0；可选10–30"></label>
          <label>实际盈亏平衡价<input name="break_even" type="number" min="0" step="any" placeholder="底仓阶段核对"></label>
        </div>
        <label class="fp-check" data-fp-standard><input name="stair_confirmed" type="checkbox">已核对新的上涨分段和上一次成交</label>
        <label class="fp-check"><input name="core_only" type="checkbox">只剩按计划保留的底仓</label>
      </details>
      <div class="fp-submit"><button type="submit">评估当前条件</button><small>手动输入 · 不计为成交 · 不下单</small></div>
    </form>
    <div class="fp-result" aria-live="polite" aria-atomic="true"><strong>尚未评估</strong><p>填写当前价格，持仓时一并填写成本和股数。</p></div>`;
  const metrics = [
    ['持仓浮盈', 'profit_pct', '%'],
    ['保护价', 'protection_price', ''],
    ['参考预算', 'entry_budget', ''],
    ['候选减仓', 'suggested_reduce_shares', ' 股'],
    ['本次计划余股', 'retain_shares', ' 股'],
    ['减仓基准', 'exit_base_shares', ' 股'],
  ];
  const checkNames = ['setup_confirmed', 'add_confirmed', 'stair_confirmed', 'core_only'];
  const numerics = ['price', 'cost', 'shares', 'equity', 'entry_stage', 'stop_price', 'exit_count', 'exit_base_shares',
    'last_exit_price', 'weak_exit_pct', 'stair_pct', 'strong_step_pct', 'retain_pct', 'break_even'];

  window.mountFormationPanel = (el, endpoint, options = {}) => {
    if (!el || el.dataset.formationMounted === 'true') return;
    el.dataset.formationMounted = 'true';
    el.classList.add('fp-panel');
    el.innerHTML = markup;
    const form = el.querySelector('form'), result = el.querySelector('.fp-result');
    const button = form.querySelector('button');
    let revision = 0;
    const add = (tag, value, parent = result) => {
      const node = document.createElement(tag);
      node.textContent = value;
      parent.appendChild(node);
      return node;
    };
    const show = (title, message, status = 'observe') => {
      result.replaceChildren();
      result.dataset.state = status;
      add('strong', title);
      if (message) add('p', message);
    };
    const sync = () => {
      const isStrong = form.elements.regime.value === 'strong';
      for (const [selector, hide] of [['[data-fp-strong]', !isStrong], ['[data-fp-standard]', isStrong]]) {
        for (const field of el.querySelectorAll(selector)) {
          field.hidden = hide;
          field.querySelector('input').disabled = hide;
        }
      }
      form.elements.retain_pct.placeholder = isStrong ? '默认20%；可选10–30' : '默认0；可选10–30';
    };
    form.addEventListener('input', () => {
      revision++;
      button.disabled = false;
      sync();
      show('待重新评估', '输入已变化，请重新核对条件。');
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const token = ++revision;
      const payload = {market: form.elements.market.value, regime: form.elements.regime.value};
      if (form.elements.entry_regime.value) payload.entry_regime = form.elements.entry_regime.value;
      for (const name of numerics) {
        const input = form.elements[name];
        if (!input.disabled && input.value !== '') payload[name] = Number(input.value);
      }
      for (const name of checkNames) payload[name] = !form.elements[name].disabled && form.elements[name].checked;
      button.disabled = true;
      show('正在评估');
      try {
        const res = await fetch(endpoint, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', ...(options.headers || {})}, body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (token !== revision) return;
        if (!res.ok) {
          const reason = [data.detail, data.error, data.message].find(x => typeof x === 'string');
          throw new Error(reason || '请检查输入后重试。');
        }
        const d = data.result || data;
        if (!d.label || !Array.isArray(d.entry_path_pct)) throw new Error('接口返回不完整，请重试。');
        const active = d.status === 'candidate';
        show(active ? '候选动作 · 待人工确认' : '观察 · 暂无候选动作', d.label, d.action === 'hard_stop' ? 'stop' : d.status);
        add('p', '建仓路径 ' + d.entry_path_pct.map((n, i) => (i ? '+' : '') + n + '%').join(' → ') + '；累计上限 ' + d.cap_pct + '%');
        const dl = add('dl', '');
        for (const [label, key, suffix] of metrics) {
          if (typeof d[key] !== 'number') continue;
          const item = add('div', '', dl);
          add('dt', label, item);
          add('dd', d[key].toLocaleString('zh-CN', {maximumFractionDigits: 4}) + suffix, item);
        }
      } catch (error) {
        if (token === revision) show('评估未完成', error.message || '请检查本地服务。');
      } finally {
        if (token === revision) button.disabled = false;
      }
    });
    sync();
  };
})();
