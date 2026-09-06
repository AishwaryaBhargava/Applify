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

/**
 * Hands the browser a file the server produced.
 *
 * The same anchor trick as `downloadTextFile`, over a Blob that already exists
 * — a `.docx` is bytes, not text, and it has to arrive through an
 * authenticated request rather than a plain link, because every route on this
 * API needs a bearer token and an `<a href>` cannot carry one.
 */
export function downloadBlob(filename: string, blob: Blob): void {
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

/**
 * The filename out of a `Content-Disposition` header, or '' when there is
 * none to read.
 *
 * `filename*=UTF-8''...` is preferred over the plain `filename=` when both are
 * present, which is what a server sends for a name with a non-ASCII character
 * in it. A caller that gets '' back names the file itself; nothing here throws,
 * because a header that cannot be parsed is not a reason to fail a download.
 */
export function filenameFromDisposition(
  header: string | null | undefined,
): string {
  if (!header) return ''
  const extended = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header)
  if (extended?.[1]) {
    try {
      return decodeURIComponent(extended[1].trim().replace(/^"|"$/g, ''))
    } catch {
      // A malformed percent-escape: fall through to the plain parameter.
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain?.[1]?.trim() ?? ''
}

export default downloadTextFile
