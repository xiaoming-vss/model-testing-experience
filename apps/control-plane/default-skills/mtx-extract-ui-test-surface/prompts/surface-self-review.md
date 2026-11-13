# UI 元素清单输出前自查


When a filesystem is available, validate the artifact with the bundled helper:

```bash
python3 scripts/validate_surface.py surface.json --source-root SOURCE_ROOT --cases cases.json --runtime-evidence runtime.json --finalize
```

Validation first checks the output schema and then the evidence relationships. Use Python jsonschema. `--finalize` attaches supplied raw evidence and normalizes metadata into its proper fields: descriptive row keys into rowKey, non-message captures into observedStates, and long interaction prose into description. It preserves those facts, IDs and references and does not promote candidates or change readiness. Omit runtime options when none was supplied. The script checks references/provenance, not live browser behavior.

Verify that local verification destinations have been read, references resolve, runtime locators retain exact provenance, and unresolved facts remain explicit. Keep credentials and tokens out of the output.
