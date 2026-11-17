const sources=[
 {id:'aqr',name:'AQR Capital Management',kind:'量化资管研究',title:'风险缓释组合的设计选择',url:'https://www.aqr.com/Insights/Research/Alternative-Thinking/Key-Design-Choices-when-Building-a-Risk-Mitigating-Portfolio',use:'借鉴信号与资产分散的研究原则。',limit:'研究涉及组合和多资产趋势，不能证明本系统的几天波段模板有效。'},
 {id:'man',name:'Man Group / Man AHL',kind:'系统化投资研究',title:'趋势跟踪与回撤',url:'https://www.man.com/insights/is-this-time-different',use:'策略需要经历不同市场环境，并关注回撤。',limit:'机构历史研究不构成本系统收益记录。'},
 {id:'ibkr',name:'Interactive Brokers',kind:'券商机制资料',title:'做空证券可用性与借券成本',url:'https://www.interactivebrokers.com/en/trading/short-securities-availability.php',use:'做空前分别核验券源与实际借券费用。',limit:'本机没有接入券商，无法确认当前可借数量或报价。'},
 {id:'quantconnect',name:'QuantConnect',kind:'量化开发与研究平台',title:'研究指南',url:'https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide',use:'先写假设，再进行样本外验证；记录成本与数据偏差。',limit:'提供研究方法，不为本系统的参数或盈利能力背书。'},
 {id:'apple',name:'Apple Developer',kind:'交互设计指南',title:'Motion · 动效',url:'https://developer.apple.com/design/human-interface-guidelines/motion',use:'动效说明状态与操作反馈，保持简短，并支持减少动态效果。',limit:'仅用于界面交互设计，与交易信号无关。'}
];
export function sourceCards(){return `<div class="source-intro"><span class="research-label">公开资料 · 2026-10-19 核验</span><h3>方法有出处，规则可追溯</h3><p>以下机构提供公开原则。本系统的KDJ/MACD阈值、2ATR和T+3/T+5是独立研究假设，尚未完成收益验证。</p></div>${sources.map(x=>`<article class="source-card" id="source-${x.id}"><small>${x.kind}</small><h3>${x.name}</h3><a href="${x.url}" target="_blank" rel="noopener noreferrer">${x.title} ↗</a><p>${x.use}</p><small>${x.limit}</small></article>`).join('')}`}
