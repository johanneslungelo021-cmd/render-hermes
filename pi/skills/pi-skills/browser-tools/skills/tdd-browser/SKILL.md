# TDD for Browser Tools

Red-Green-Refactor loop for scrapers and publishers:

1. **Red** — Write the schema (your failing test). Call `validateSchema(schema)` to catch malformed schemas.
2. **Green** — Extract with `browser_scrape(schema: {...})`. Iterate selectors until data appears.
3. **Refactor** — Add `assert: true` to validate required fields. Fix selectors until `assertSchema()` passes.

Key principle: the schema IS the test. Required fields + non-null assertions replace assertion libraries.
