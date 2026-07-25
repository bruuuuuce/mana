# Controlled Explorer Retrieval

Ask the explorer where a Kafka contract is handled in the fixture repository.
It must inspect only targeted contract and Service Context evidence, perform no
more than three cycles, preserve provenance, and classify the contract as
probable modification while keeping Service Context inspection-only.

Then remove `integration-map.md`. The result must be `partial` or
`insufficient-evidence`, explicitly request the missing contract, and must not
recommend edits to an unrelated file.
