# Context for engineers and AI agents — ApexIntegrationsAPI (Docuflow server + web portal)

Start with `docs/README.md`. Non-negotiables learned the hard way:

1. **Before every push**: `python3 scripts/localcheck.py` (Django system check + migration parity with stub env).
   `py_compile` is not enough — a missing import in `urls.py` took production down once.
2. **Deploy order** on PythonAnywhere: `git pull` → `python manage.py migrate` → reload. Say "has a migration" in
   every deploy note.
3. **Web portal**: edit `web/src`, run `cd web && npm run build`, commit `web/dist`. The server has no Node.
4. **Deal visibility** goes through `views.deals_for(user)`. Never filter deals by `agent=request.user` directly.
5. **DocuSign**: never `DocuSignService()` bare in a deal context — use `env_for_user(owner)` when creating an
   envelope and the row's `docusign_env` when acting on an existing one.
6. **PDF templates lie**: AcroForm field names are frequently mislabeled. Verify by rendering markers before mapping.
7. **Keys shared with iOS must not drift**: RE-21 JSON keys (`RE21FormData` property names), checklist task keys
   (`p1.1…p4.5`), deadline rules, `PacketPayloadBuilder` body shape.
8. **New endpoint ⇒** add it to `web/src/endpoints.ts` (API Explorer) and `web/src/api.ts`.
9. **Secrets** only in the server `.env` / `.pem` files (gitignored). Runtime switches go in `AppSetting`.
10. **Contracts must never default to the owner's identity**; identity is stamped from the deal's agent.
11. MLS data is always live (no mock toggle); the credential never leaves the server.
12. The `000000` OTP bypass is for the owner account only.
