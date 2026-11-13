# UI 场景设计输出前自查

Build the design as structured data, copying original titles, prerequisites and source excerpts from the supplied JSON rather than retyping them. Keep working data in temporary files, inspect targeted cases, and avoid repeatedly dumping the complete source/design into the context. Use a JSON serializer for the final object, then parse and validate that saved JSON. Keep action summaries and repeated capability reasons concise; never shorten original source excerpts, omit clauses or drop cases to reduce output size. Deliver the saved serialization unchanged as the final JSON object. Do not reconstruct it from memory, interleave narration, add Markdown fences, or append self-correction text to a malformed response. For a format repair, fix the serialized object and validate it; preserve unaffected business classifications instead of rebuilding the entire module.

The validator reads the temporary JSON candidate and the current module's original cases. Save the caller’s capability declaration unchanged as `caller-capabilities.json` and pass it explicitly; use the built-in default only when no caller profile was supplied. A default-profile mismatch is not a reason to rewrite the caller’s declared capabilities:

```bash
python3 scripts/validate_scenarios.py scenarios.json --cases cases.json --capabilities caller-capabilities.json
```

Pass `--execution-profile` as well when the caller supplies an executor profile. The checker enforces the complete schema, source order and the shared action/expectation ID namespace. This checks source accounting and design structure, not execution readiness. Temporary validation files do not change the direct-response delivery contract. Review exclusions and core relationships semantically. Version 1 artifacts are supported by the legacy validator only; new generation uses version 2.
