type ArtifactMedia = 'image/png' | 'application/zip'

// Only object URLs produced by this page's live debug stream are accepted.
const liveUrls = new Map<string, ArtifactMedia>()

export function createLiveArtifactUrl(chunks: Uint8Array<ArrayBuffer>[], media: ArtifactMedia) {
  const url = URL.createObjectURL(new Blob(chunks, { type: media }))
  liveUrls.set(url, media)
  return url
}

export function liveArtifactMedia(url: string) {
  return liveUrls.get(url)
}

export function revokeLiveArtifactUrl(url: string) {
  if (liveUrls.delete(url)) URL.revokeObjectURL(url)
}
