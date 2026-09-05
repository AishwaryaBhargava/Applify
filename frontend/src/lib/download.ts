/**
 * Hands the browser a text file to save.
 *
 * A Blob URL plus a synthetic anchor click is the only way to save generated
 * text without a round trip to a server that never had the file. The object
 * URL is revoked on the next frame — immediately after the click would race
 * the download in Safari, and never revoking it leaks the blob for the life of
 * the tab.
 */
export function downloadTextFile(
  filename: string,
  content: string,
  mimeType = 'text/markdown;charset=utf-8',
): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  anchor.style.display = 'none'

  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)

  setTimeout(() => URL.revokeObjectURL(url), 0)
}

export default downloadTextFile
