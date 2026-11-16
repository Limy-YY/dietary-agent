import MarkdownIt from 'markdown-it'

// html:false —— 原始 HTML 一律转义，防止 LLM 输出注入脚本/标签（XSS）。
// linkify:true —— 裸 URL 自动变链接；breaks:true —— 换行转 <br>，匹配模型输出的多行正文。
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

export function renderMarkdown(text) {
  if (!text) return ''
  return md.render(String(text))
}
