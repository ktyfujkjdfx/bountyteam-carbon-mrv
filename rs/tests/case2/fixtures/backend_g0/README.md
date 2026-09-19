# Backend G0 contract notes

The integrated repository has one authoritative contract source:

- `contracts/v2/internal-models.v2.schema.json` for the RS/Backend boundary;
- `contracts/v2/api-models.v2.schema.json` and `contracts/v2/openapi.v2.yaml`
  for HTTP consumers.

RS contract tests resolve the root schema from the test file location,
independent of the current working directory. A missing root schema fails with
an explicit message. Schema copies are intentionally not stored here because
they create a second editable authority and can drift from Backend during
parallel component development.

The final root schema accepts nullable AGB and AGB SD for invalid cells and
contains the raw coverage, signed area difference, structured warnings and
traceability fields required by the reviewed RS payload.
