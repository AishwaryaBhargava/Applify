import api, { apiErrorMessage, apiErrorStatus } from './api'

/**
 * Outcome of `DELETE /account`.
 *
 * A failure is returned rather than thrown because two of the three failures
 * are not faults the user can retry away: a server with no service-role key
 * cannot delete anyone (501), and a server that deleted the data but could not
 * remove the login (502) has already done half the job. Both need their own
 * wording, so the status travels with the message.
 */
export type DeleteAccountResult =
  | { ok: true }
  | { ok: false; status?: number; message: string }

/** The 501 the backend sends when deletion is not configured on this server. */
export const DELETION_UNAVAILABLE_STATUS = 501

/**
 * DELETE /account — removes the profile, chats, outputs, tracker entries, and
 * the login itself.
 *
 * There is no undo and no soft delete, so the caller is expected to have made
 * the user type the word DELETE first.
 */
export async function deleteAccount(): Promise<DeleteAccountResult> {
  try {
    await api.delete('/account')
    return { ok: true }
  } catch (error) {
    return {
      ok: false,
      status: apiErrorStatus(error),
      message: apiErrorMessage(
        error,
        'We could not delete your account. Please try again.',
      ),
    }
  }
}

export default deleteAccount
