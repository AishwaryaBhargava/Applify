import api from './api'
import { streamSSE, type StreamHandlers } from './messages'
import { filenameFromDisposition } from '../lib/download'
import type { GeneratedOutput, OutputType } from '../types'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface OutputRequest {
  output_type: OutputType
  /** A steer for a resume or cover letter; the question itself for an answer. */
  user_context?: string
}

/** Absolute URL of the SSE output endpoint. */
export function outputStreamUrl(chatId: string): string {
  return `${baseURL}/chats/${chatId}/outputs`
}

/**
 * POST /chats/{id}/outputs — the explicit-button path to a document.
 *
 * Answers with the same SSE stream as a chat message (start / token / done /
 * error), with `kind` fixed to the requested `output_type`, and persists the
 * user turn the button stands for before the first frame. So the only thing
 * this adds over `streamMessage` is the URL and the body.
 */
export async function streamOutput(
  chatId: string,
  payload: OutputRequest,
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE(outputStreamUrl(chatId), payload, handlers, signal)
}

/** GET /chats/{id}/outputs — documents already generated here, newest first. */
export async function listOutputs(chatId: string): Promise<GeneratedOutput[]> {
  const { data } = await api.get<GeneratedOutput[]>(`/chats/${chatId}/outputs`)
  return data
}

/** The two file formats `GET .../export` renders a stored document into. */
export type ExportFormat = 'docx' | 'md'

export interface ExportedOutput {
  blob: Blob
  /** The server's `Content-Disposition` name; '' when it did not send one. */
  filename: string
}

/**
 * GET /chats/{id}/outputs/{output_id}/export?format= — the document as a file.
 *
 * Requested through the shared Axios instance rather than a link so the
 * bearer token the interceptor adds actually goes with it: every route on this
 * API needs one, and an `<a href download>` cannot carry a header. The body
 * comes back as a Blob and `lib/download.downloadBlob` hands it to the
 * browser.
 *
 * The server names the file; `filename` is empty when it did not, and the
 * caller falls back to the company-plus-type name the markdown download uses.
 */
export async function exportOutput(
  chatId: string,
  outputId: string,
  format: ExportFormat,
): Promise<ExportedOutput> {
  const response = await api.get<Blob>(
    `/chats/${chatId}/outputs/${outputId}/export`,
    { params: { format }, responseType: 'blob' },
  )
  return {
    blob: response.data,
    filename: filenameFromDisposition(
      // Axios lower-cases response header names, but a proxy that does not is
      // not worth a broken download.
      response.headers['content-disposition'] ??
        (response.headers as Record<string, string>)['Content-Disposition'],
    ),
  }
}
