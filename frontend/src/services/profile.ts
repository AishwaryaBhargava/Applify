import api from './api'
import type { Profile, ParsedProfile, ProfileGap } from '../types'

/** POST /profile/upload — multipart resume upload (PDF or DOCX). */
export async function uploadResume(file: File): Promise<Profile> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<Profile>('/profile/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** GET /profile — current user's full profile. */
export async function getProfile(): Promise<Profile> {
  const { data } = await api.get<Profile>('/profile')
  return data
}

/** PATCH /profile — partial profile update, merged server side. */
export async function updateProfile(
  patch: Partial<ParsedProfile>,
): Promise<Profile> {
  const { data } = await api.patch<Profile>('/profile', patch)
  return data
}

/** GET /profile/gaps — thin or missing profile sections. */
export async function getProfileGaps(): Promise<ProfileGap[]> {
  const { data } = await api.get<ProfileGap[]>('/profile/gaps')
  return data
}
