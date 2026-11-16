import MarkdownIt from 'markdown-it'

// html:false —— 原始 HTML 一律转义，防止 LLM 输出注入脚本/标签（XSS）。
// linkify:true —— 裸 URL 自动变链接；breaks:true —— 换行转 <br>，匹配模型输出的多行正文。
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
// 开启 GFM 表格 / 删除线（markdown-it 的 default 预设已含，这里显式声明以防预设变动）。
md.enable(['table', 'strikethrough'])

// LLM 常把表格写成「制表符分隔」而不是 GFM 的「| … | … |」；这里把连续的制表符行转成竖线表格。
function normalizeTables(text) {
  const lines = text.split('\n')
  const out = []
  let i = 0
  while (i < lines.length) {
    if (!lines[i].includes('\t')) {
      out.push(lines[i])
      i++
      continue
    }
    // 收集连续含制表符的行，作为一个表格（至少表头 + 1 行数据才转换，避免误伤普通文本）
    const run = []
    while (i < lines.length && lines[i].includes('\t')) {
      run.push(lines[i].split('\t').map((c) => c.trim()))
      i++
    }
    if (run.length < 2) {
      for (const r of run) out.push(r.join(' '))
      continue
    }
    const cols = Math.max(...run.map((r) => r.length))
    const cell = (c) => (c == null ? '' : String(c)).replace(/\|/g, '\\|')
    const row = (r) => '| ' + Array.from({ length: cols }, (_, j) => cell(r[j])).join(' | ') + ' |'
    out.push(row(run[0]))
    out.push('|' + Array.from({ length: cols }, () => '---').join('|') + '|')
    for (const r of run.slice(1)) out.push(row(r))
  }
  return out.join('\n')
}

export function renderMarkdown(text) {
  if (!text) return ''
  return md.render(normalizeTables(String(text)))
}
