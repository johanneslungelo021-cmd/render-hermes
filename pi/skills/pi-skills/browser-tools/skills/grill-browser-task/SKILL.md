# Grill Browser Task

Before any browser automation, produce a TaskSpec by answering 8 questions:

1. **Intent** — What exactly are you trying to do?
2. **Action type** — scrape, publish, monitor, or search?
3. **Target URL** — exact URL
4. **Idle time** — how long to wait for page load?
5. **Success criteria** — what proves it worked?
6. **Failure modes** — what could go wrong?
7. **Schema** — what data to extract? (for scrape)
8. **Actions** — what UI actions? (for publish)

Call `agent_grill(description: "...")` to generate a spec, or `agent_grill(answers: {...})` to validate one.
