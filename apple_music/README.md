# Apple Music worker

Start with the [setup guide](../docs/SETUP.md). Use [download.py](download.py) for local downloads. It owns the worker subprocess and confirms each track after saving it to the destination.

The worker integrates [GAMDL](https://github.com/glomatico/gamdl). Its external service adapters reference [WorldObservationLog/wrapper](https://github.com/WorldObservationLog/wrapper) and [glomatico/wrapper-v2](https://github.com/glomatico/wrapper-v2). Upstream components are maintained and licensed separately.

[The source manifest](source-manifest.json) records checksums for the extracted integration modules. Run [demo.py](demo.py) to exercise FLAC conversion with a generated ALAC tone.
