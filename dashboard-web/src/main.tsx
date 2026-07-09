import { createRoot } from 'react-dom/client'
import App from './App'
import { HTML_LANG, lang, t } from './i18n'
import './tokens.css'

// index.html 是静态产物，没法按语言预渲染，所以 title 和 <html lang> 在挂载前改。
// 品牌名不进词典（station 的心跳探测靠它判断品牌完整性）。
document.documentElement.lang = HTML_LANG[lang]
document.title = `察元AI工舱 · ${t('Workstation Dashboard')}`

createRoot(document.getElementById('root')!).render(<App />)
