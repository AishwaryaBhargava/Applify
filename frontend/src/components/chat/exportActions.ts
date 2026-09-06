import { exportOutput, type ExportFormat } from '../../services/outputs'
import { apiErrorMessage } from '../../services/api'
import { downloadBlob } from '../../lib/download'
import { pushToast } from '../../store/toastStore'
import type { GeneratedOutput, ThreadMessage } from '../../types'

/**
 * The `generated_outputs` row a document bubble was filed under, or null when
 * there is none to point at.
 *
 * A thread message carries its own id, not the output's, so the two have to be
 * paired here. Exact content is the reliable key — the server stores the
 * finished document verbatim — and the newest output of the same type is the
 * fallback for a bubble whose text was normalised on the way in. A partial
 * document is deliberately never matched: a half-streamed resume is not filed
 * as an output, so there is nothing on the server to export.
 */
export function outputIdForMessage(
  outputs: GeneratedOutput[],
  message: ThreadMessage,
): string | null {
  if (message.pending || message.errored) return null

  const sameType = outputs.filter(
    (output) => output.output_type === (message.kind as GeneratedOutput['output_type']),
  )
  if (sameType.length === 0) return null

  const exact = sameType.find((output) => output.content === message.content)
  // `outputs` arrives newest first, so index 0 is the closest guess.
  return (exact ?? sameType[0]).id
}

/**
 * Fetches a stored document in the requested format and hands it to the
 * browser.
 *
 * The request goes through Axios rather than a link because every route needs
 * a bearer token; the server names the file, and `fallbackName` covers a
 * response that did not send a `Content-Disposition`.
 *
 * Resolves to whether the file was saved, so a caller can stop spinning either
 * way. Failure is a toast: nothing on the page changed, and the document is
 * still readable in the thread.
 */
export async function downloadOutputFile(
  chatId: string,
  outputId: string,
  format: ExportFormat,
  fallbackName: string,
): Promise<boolean> {
  try {
    const { blob, filename } = await exportOutput(chatId, outputId, format)
    downloadBlob(filename || fallbackName, blob)
    return true
  } catch (error) {
    pushToast(
      apiErrorMessage(error, `That ${format.toUpperCase()} could not be built.`),
      'error',
    )
    return false
  }
}

/** The print view's route, opened in a new tab so the chat stays where it is. */
export function printOutputPath(chatId: string, outputId: string): string {
  return `/print/outputs/${chatId}/${outputId}`
}
