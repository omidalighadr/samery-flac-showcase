# Changelog

## 2026-11-20

The public download integration was refreshed from the application source.
Only the selected download modules were extracted; the private Telegram
application and its configuration are outside this repository.

### Download checks

- Require successful, nonempty media transport; unavailable fragments fail the
  download instead of being silently skipped.
- Retry selected transient transport failures with a bounded attempt count.
- Compare decoded output duration with catalog duration when supplied, then run
  a complete decode before emitting a successful track event.
- Retain strict ALAC-to-FLAC conversion and decoded PCM comparison.

### Catalog and account handling

- Include bounded catalog pagination, duplicate-ID removal and disc/track sorting
  for albums. Playlist order is kept for distinct song IDs.
- Include the current account-bootstrap retries and safe error categories.
- Keep account credentials from being followed to redirect destinations.

### Local output

- Use the current metadata filename helper for readable artist/title names.
- Prefix whole-album output with disc/track numbers.
- Expose `--lyrics` to request available synchronized lyrics, which the worker
  can embed in the FLAC tags. The CLI does not export lyric sidecars.
- Preserve existing destination files by choosing an unused numbered filename.

### Validation and scope

- Expand the offline test suite to 27 tests, including generated lossless audio.
- Run source-checksum and public-source privacy regressions in CI.
- Publish a selected source manifest without private configuration, account
  material, database state, media, third-party binaries or dependency wheels.
- Channel publishing, Telegram API transport, album cards and the Telegram ZIP
  workflow remain part of the private application; they are not CLI features.
