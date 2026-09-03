# Dependency rules

The project enforces a small layered dependency model with `python scripts/check_architecture.py`.

```text
web/blueprints -> services -> domain + repositories -> infrastructure
```

- `domain/` is framework-independent and cannot import Flask, web, services, or repositories.
- `infrastructure/` cannot depend on the web layer.
- `repositories/` cannot depend on routes or services.
- `services/` cannot depend on the web layer.
- Routes translate HTTP input/output and delegate application work.
- Cross-layer exceptions should be explicit; update the checker and this document together.
