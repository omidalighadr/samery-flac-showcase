# Apple Music worker

Start with the [setup guide](../docs/SETUP.md). Use [download.py](download.py) for local downloads. It owns the worker subprocess and confirms each track after saving it to the destination.

The worker integrates [GAMDL](https://github.com/glomatico/gamdl). Its external service adapters reference [WorldObservationLog/wrapper](https://github.com/WorldObservationLog/wrapper) and [glomatico/wrapper-v2](https://github.com/glomatico/wrapper-v2). Upstream components are maintained and licensed separately.

[The source manifest](source-manifest.json) records checksums for the extracted integration modules. Run [demo.py](demo.py) to exercise FLAC conversion with a generated ALAC tone.


## Current integration modules

`apple_stream.py` handles fragment transport retries and output duration/decode
checks. `apple_collection_catalog.py` reads bounded album/playlist catalog pages.
`apple_session.py` provides the current account bootstrap and safe error codes.
`music_metadata.py` handles tags, artwork previews and public filenames. The
other selected modules and their checksums are listed in the source manifest.

The public CLI has no Telegram API settings or private bot handlers. Album cards,
channel publishing, large-file delivery and Telegram ZIP commands are separate
application features. This repository does not include the external service or
account credentials needed for live operation.
