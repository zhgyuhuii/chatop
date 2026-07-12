import { useEffect, useRef } from 'react'

// 把 0/1 矩阵画成黑白二维码。matrix 来自引擎 openclaw_qr.parse_ascii_qr（经 SSE 送达）。
export default function QrCanvas({ matrix, box = 6, quiet = 4 }: {
  matrix: number[][]; box?: number; quiet?: number
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current
    if (!cv || !matrix?.length) return
    const n = matrix.length
    const size = (n + quiet * 2) * box
    cv.width = size; cv.height = size
    const ctx = cv.getContext('2d')!
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, size, size)
    ctx.fillStyle = '#000'
    for (let y = 0; y < n; y++)
      for (let x = 0; x < (matrix[y]?.length || 0); x++)
        if (matrix[y][x]) ctx.fillRect((x + quiet) * box, (y + quiet) * box, box, box)
  }, [matrix, box, quiet])
  return <canvas ref={ref} style={{ background: '#fff', borderRadius: 8 }} />
}
