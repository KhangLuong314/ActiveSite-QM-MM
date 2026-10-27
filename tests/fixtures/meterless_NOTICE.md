# Third-party notice: Meterless H-MEM conformance vectors

`meterless_hmem_vectors.json` is an unmodified copy of a file from the Meterless project.

- Source repository: https://github.com/meterless/meterless
- Path: `engines/hmem/conformance/vectors/vectors.json`
- Upstream commit: `0aa7417`
- SHA-256 of the copied file: `10afb5a07233466576ba6feb0d88408488909ba2721ee9157fdb932132917029`
- License: Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0)

The file is not edited. `tests/test_hmem_conformance.py` reads it and applies the
same assertions as upstream `engines/hmem/conformance/runner.ts`.
